import Foundation
import Vision
import AppKit
// 用 macOS 自带 Vision 识别图片里的中文文字，逐帧输出：帧名<TAB>文字(每块用|分隔，带纵向位置)
let dir = CommandLine.arguments[1]
let files = try! FileManager.default.contentsOfDirectory(atPath: dir).filter{$0.hasSuffix(".jpg")}.sorted()
for f in files {
  guard let img = NSImage(contentsOfFile: dir + "/" + f), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
  let req = VNRecognizeTextRequest()
  req.recognitionLevel = .accurate
  req.recognitionLanguages = ["zh-Hans", "en-US"]
  req.usesLanguageCorrection = true
  try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
  let obs = (req.results ?? []).compactMap { o -> String? in
    guard let t = o.topCandidates(1).first else { return nil }
    return String(format: "%.2f:", o.boundingBox.midY) + t.string
  }
  print(f + "\t" + obs.joined(separator: "|"))
}
