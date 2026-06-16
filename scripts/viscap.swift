// cortex-vision native capture helper.
//
// On-device image capture + analysis for the cortex-vision MCP. Grabs an image
// from one of three sources (screen, image file, camera), runs an Apple Vision
// task (OCR, scene labels, or barcodes) on-device, and emits a single JSON
// object on stdout.
//
// Modes:
//   viscap --check-auth
//   viscap --capture --source screen|file|camera --task ocr|scene|barcode
//          [--path P] [--region x,y,w,h] [--max-results N]
//
// Output (capture): {"text": "...", "labels": [{"label","confidence"}],
//                    "barcodes": [{"payload","symbology"}], "source": "...",
//                    "duration": seconds, "on_device": bool}
// Output (auth):    {"camera_auth": "...", "screen_recording": "..."}
// Output (failure): {"error": "message"}  (exit 1)

import AVFoundation
import AppKit
import CoreImage
import Foundation
import Vision

func emit(_ obj: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: obj),
        let s = String(data: data, encoding: .utf8)
    {
        print(s)
    }
}

func fail(_ message: String) -> Never {
    emit(["error": message])
    exit(1)
}

func argValue(_ name: String, _ fallback: String) -> String {
    let a = CommandLine.arguments
    if let i = a.firstIndex(of: name), i + 1 < a.count { return a[i + 1] }
    return fallback
}

// MARK: - Authorization

func cameraAuthStatus() -> String {
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized: return "authorized"
    case .denied: return "denied"
    case .restricted: return "restricted"
    case .notDetermined: return "notDetermined"
    @unknown default: return "unknown"
    }
}

func requestCameraAuth() -> String {
    if AVCaptureDevice.authorizationStatus(for: .video) == .notDetermined {
        let sem = DispatchSemaphore(value: 0)
        AVCaptureDevice.requestAccess(for: .video) { _ in sem.signal() }
        sem.wait()
    }
    return cameraAuthStatus()
}

func screenRecordingStatus() -> String {
    // CGPreflightScreenCaptureAccess() reports current grant without prompting.
    return CGPreflightScreenCaptureAccess() ? "authorized" : "denied"
}

// MARK: - Image acquisition

func cgImageFromFile(_ path: String) -> CGImage {
    let url = URL(fileURLWithPath: path)
    guard FileManager.default.fileExists(atPath: path) else {
        fail("image file not found: \(path)")
    }
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
        let img = CGImageSourceCreateImageAtIndex(src, 0, nil)
    else {
        fail("could not decode image at \(path)")
    }
    return img
}

func cgImageFromScreen(region: String?) -> CGImage {
    // Use the `screencapture` CLI (silent, -x). It honours Screen Recording
    // permission; ScreenCaptureKit would add async machinery without changing
    // the permission requirement. Region is "x,y,w,h" in screen points.
    let tmp = NSTemporaryDirectory() + "cortex-vision-\(ProcessInfo.processInfo.processIdentifier).png"
    var args = ["-x", "-t", "png"]
    if let region = region, !region.isEmpty {
        let parts = region.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }
        if parts.count == 4 {
            args += ["-R", parts.joined(separator: ",")]
        } else {
            fail("region must be 'x,y,w,h'")
        }
    }
    args.append(tmp)
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    proc.arguments = args
    do { try proc.run() } catch {
        fail("screencapture failed to launch: \(error.localizedDescription)")
    }
    proc.waitUntilExit()
    guard FileManager.default.fileExists(atPath: tmp) else {
        fail("screen capture produced no image — grant Screen Recording permission")
    }
    let img = cgImageFromFile(tmp)
    try? FileManager.default.removeItem(atPath: tmp)
    return img
}

final class FrameGrabber: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let sem = DispatchSemaphore(value: 0)
    var image: CGImage?
    private let ciContext = CIContext()

    func captureOutput(
        _ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        if image != nil { return }
        guard let pixel = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let ci = CIImage(cvPixelBuffer: pixel)
        if let cg = ciContext.createCGImage(ci, from: ci.extent) {
            image = cg
            sem.signal()
        }
    }
}

func cgImageFromCamera() -> CGImage {
    let auth = requestCameraAuth()
    guard auth == "authorized" else { fail("camera not authorized: \(auth)") }
    guard let device = AVCaptureDevice.default(for: .video) else {
        fail("no camera device available")
    }
    let session = AVCaptureSession()
    session.sessionPreset = .photo
    do {
        let input = try AVCaptureDeviceInput(device: device)
        guard session.canAddInput(input) else { fail("cannot add camera input") }
        session.addInput(input)
    } catch {
        fail("camera input failed: \(error.localizedDescription)")
    }
    let output = AVCaptureVideoDataOutput()
    output.videoSettings = [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
    ]
    let grabber = FrameGrabber()
    output.setSampleBufferDelegate(grabber, queue: DispatchQueue(label: "cortex-vision.camera"))
    guard session.canAddOutput(output) else { fail("cannot add camera output") }
    session.addOutput(output)
    session.startRunning()
    let got = grabber.sem.wait(timeout: .now() + 10)
    session.stopRunning()
    guard got == .success, let img = grabber.image else {
        fail("camera produced no frame within 10s")
    }
    return img
}

func acquire(source: String, path: String?, region: String?) -> CGImage {
    switch source {
    case "file":
        guard let path = path else { fail("source='file' requires --path") }
        return cgImageFromFile(path)
    case "screen":
        return cgImageFromScreen(region: region)
    case "camera":
        return cgImageFromCamera()
    default:
        fail("unknown source \(source)")
    }
}

// MARK: - Vision tasks

func runOCR(_ image: CGImage) -> (String, Double) {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do { try handler.perform([request]) } catch {
        fail("OCR failed: \(error.localizedDescription)")
    }
    let observations = request.results ?? []
    var lines: [String] = []
    var confSum = 0.0
    var confCount = 0
    for obs in observations {
        guard let top = obs.topCandidates(1).first else { continue }
        lines.append(top.string)
        confSum += Double(top.confidence)
        confCount += 1
    }
    let conf = confCount > 0 ? confSum / Double(confCount) : 0.0
    return (lines.joined(separator: "\n"), conf)
}

func runScene(_ image: CGImage, maxResults: Int) -> [[String: Any]] {
    let request = VNClassifyImageRequest()
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do { try handler.perform([request]) } catch {
        fail("scene classification failed: \(error.localizedDescription)")
    }
    let observations = (request.results ?? [])
        .filter { $0.confidence > 0.1 }
        .sorted { $0.confidence > $1.confidence }
        .prefix(maxResults)
    return observations.map {
        ["label": $0.identifier, "confidence": Double($0.confidence)]
    }
}

func runBarcode(_ image: CGImage, maxResults: Int) -> [[String: Any]] {
    let request = VNDetectBarcodesRequest()
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do { try handler.perform([request]) } catch {
        fail("barcode detection failed: \(error.localizedDescription)")
    }
    let observations = (request.results ?? []).prefix(maxResults)
    return observations.map {
        [
            "payload": $0.payloadStringValue ?? "",
            "symbology": $0.symbology.rawValue,
            "confidence": Double($0.confidence),
        ]
    }
}

func capture(source: String, task: String, path: String?, region: String?, maxResults: Int) -> Never {
    let start = Date()
    let image = acquire(source: source, path: path, region: region)
    var out: [String: Any] = ["source": source, "on_device": true]
    switch task {
    case "ocr":
        let (text, conf) = runOCR(image)
        out["text"] = text
        out["confidence"] = conf
        out["labels"] = []
        out["barcodes"] = []
    case "scene":
        out["text"] = ""
        out["labels"] = runScene(image, maxResults: maxResults)
        out["barcodes"] = []
    case "barcode":
        out["text"] = ""
        out["labels"] = []
        out["barcodes"] = runBarcode(image, maxResults: maxResults)
    default:
        fail("unknown task \(task)")
    }
    out["duration"] = Date().timeIntervalSince(start)
    emit(out)
    exit(0)
}

// MARK: - Entry

let mode = CommandLine.arguments.dropFirst().first ?? "--capture"
switch mode {
case "--check-auth":
    let camera = requestCameraAuth()
    let screen = screenRecordingStatus()
    emit(["camera_auth": camera, "screen_recording": screen])
    exit(0)
case "--capture":
    let source = argValue("--source", "screen")
    let task = argValue("--task", "ocr")
    let path = CommandLine.arguments.contains("--path") ? argValue("--path", "") : nil
    let region = CommandLine.arguments.contains("--region") ? argValue("--region", "") : nil
    let maxResults = Int(argValue("--max-results", "50")) ?? 50
    capture(source: source, task: task, path: path, region: region, maxResults: maxResults)
default:
    fail("unknown mode \(mode)")
}
