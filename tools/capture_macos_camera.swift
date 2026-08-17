#!/usr/bin/env swift
// One-shot AVFoundation camera provider for the release HIL camera subset.
// It is intentionally a foreground command, not a daemon or macOS service.

import AppKit
import AVFoundation
import Foundation

enum CaptureFailure: Error, CustomStringConvertible {
    case usage(String)
    case denied
    case unavailable(String)
    case configuration(String)
    case timeout
    case encoding

    var description: String {
        switch self {
        case .usage(let message): return message
        case .denied: return "camera access was not granted"
        case .unavailable(let message): return message
        case .configuration(let message): return message
        case .timeout: return "camera capture timed out"
        case .encoding: return "camera frame could not be encoded as PNG"
        }
    }
}

final class PhotoReceiver: NSObject, AVCapturePhotoCaptureDelegate {
    let finished = DispatchSemaphore(value: 0)
    var data: Data?
    var failure: Error?

    func photoOutput(
        _ output: AVCapturePhotoOutput,
        didFinishProcessingPhoto photo: AVCapturePhoto,
        error: Error?
    ) {
        if let error = error {
            failure = error
        } else {
            data = photo.fileDataRepresentation()
        }
        finished.signal()
    }
}

func jsonLine(_ object: [String: Any]) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    guard let line = String(data: data, encoding: .utf8) else {
        throw CaptureFailure.encoding
    }
    print(line)
}

func cameras() -> [AVCaptureDevice] {
    let discovery = AVCaptureDevice.DiscoverySession(
        deviceTypes: [.builtInWideAngleCamera, .externalUnknown],
        mediaType: .video,
        position: .unspecified
    )
    return discovery.devices.sorted { $0.uniqueID < $1.uniqueID }
}

func authorize() throws {
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized:
        return
    case .notDetermined:
        let answered = DispatchSemaphore(value: 0)
        var granted = false
        AVCaptureDevice.requestAccess(for: .video) { allowed in
            granted = allowed
            answered.signal()
        }
        if answered.wait(timeout: .now() + 30) == .timedOut || !granted {
            throw CaptureFailure.denied
        }
    default:
        throw CaptureFailure.denied
    }
}

func pngData(from captured: Data) throws -> Data {
    guard let image = NSImage(data: captured),
          let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let png = bitmap.representation(using: .png, properties: [:]) else {
        throw CaptureFailure.encoding
    }
    return png
}

func listCameras() throws {
    let values: [[String: Any]] = cameras().map { device in
        [
            "id": device.uniqueID,
            "name": device.localizedName,
            "connected": device.isConnected,
            "suspended": device.isSuspended,
        ]
    }
    try jsonLine([
        "schema": "leshy.camera_provider.devices.v1",
        "devices": values,
    ])
}

func capture(deviceID: String, output: URL, warmupMilliseconds: Int) throws {
    try authorize()
    guard let device = cameras().first(where: { $0.uniqueID == deviceID }) else {
        throw CaptureFailure.unavailable("camera id not found: \(deviceID)")
    }
    guard device.isConnected && !device.isSuspended else {
        throw CaptureFailure.unavailable("camera is not ready: \(device.localizedName)")
    }
    if FileManager.default.fileExists(atPath: output.path) {
        throw CaptureFailure.configuration("refusing to overwrite: \(output.path)")
    }
    let parent = output.deletingLastPathComponent()
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: parent.path, isDirectory: &isDirectory),
          isDirectory.boolValue else {
        throw CaptureFailure.configuration("output directory does not exist: \(parent.path)")
    }

    let session = AVCaptureSession()
    session.beginConfiguration()
    session.sessionPreset = .photo
    let input = try AVCaptureDeviceInput(device: device)
    let photoOutput = AVCapturePhotoOutput()
    guard session.canAddInput(input), session.canAddOutput(photoOutput) else {
        throw CaptureFailure.configuration("camera cannot be added to capture session")
    }
    session.addInput(input)
    session.addOutput(photoOutput)
    session.commitConfiguration()
    session.startRunning()
    defer { session.stopRunning() }
    Thread.sleep(forTimeInterval: Double(warmupMilliseconds) / 1000.0)

    let receiver = PhotoReceiver()
    let settings = AVCapturePhotoSettings(
        format: [AVVideoCodecKey: AVVideoCodecType.jpeg]
    )
    photoOutput.capturePhoto(with: settings, delegate: receiver)
    guard receiver.finished.wait(timeout: .now() + 15) == .success else {
        throw CaptureFailure.timeout
    }
    if let failure = receiver.failure {
        throw failure
    }
    guard let captured = receiver.data else {
        throw CaptureFailure.encoding
    }
    let png = try pngData(from: captured)
    try png.write(to: output, options: .withoutOverwriting)
    try jsonLine([
        "schema": "leshy.camera_provider.capture.v1",
        "camera_id": device.uniqueID,
        "camera_name": device.localizedName,
        "output": output.path,
        "png_bytes": png.count,
    ])
}

func option(_ name: String, in arguments: [String]) throws -> String {
    guard let index = arguments.firstIndex(of: name), index + 1 < arguments.count else {
        throw CaptureFailure.usage("missing \(name)")
    }
    return arguments[index + 1]
}

func main() throws {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard let command = arguments.first else {
        throw CaptureFailure.usage("usage: capture_macos_camera.swift list|capture")
    }
    if command == "list" {
        try listCameras()
        return
    }
    guard command == "capture" else {
        throw CaptureFailure.usage("unknown command: \(command)")
    }
    let deviceID = try option("--device-id", in: arguments)
    let output = URL(fileURLWithPath: try option("--output", in: arguments))
    let warmupText = (try? option("--warmup-ms", in: arguments)) ?? "1200"
    guard let warmup = Int(warmupText), (0...10_000).contains(warmup) else {
        throw CaptureFailure.usage("--warmup-ms must be between 0 and 10000")
    }
    try capture(deviceID: deviceID, output: output, warmupMilliseconds: warmup)
}

do {
    try main()
} catch {
    FileHandle.standardError.write(Data("camera provider: FAIL: \(error)\n".utf8))
    exit(1)
}
