import AppKit

let output = CommandLine.arguments[1]
let size = 1024
let rep = NSBitmapImageRep(
  bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8, samplesPerPixel: 4,
  hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
let box = NSRect(x: 52, y: 52, width: 920, height: 920)
let background = NSBezierPath(roundedRect: box, xRadius: 210, yRadius: 210)
NSGradient(
  starting: NSColor(calibratedRed: 0.055, green: 0.17, blue: 0.19, alpha: 1),
  ending: NSColor(calibratedRed: 0.018, green: 0.035, blue: 0.085, alpha: 1))!.draw(
    in: background, angle: 65)
NSColor(calibratedRed: 0.2, green: 0.9, blue: 0.64, alpha: 0.25).setStroke()
background.lineWidth = 5
background.stroke()
let halo = NSBezierPath(ovalIn: NSRect(x: 187, y: 187, width: 650, height: 650))
NSColor(calibratedRed: 0.16, green: 0.9, blue: 0.61, alpha: 0.07).setFill()
halo.fill()
NSColor(calibratedRed: 0.2, green: 0.9, blue: 0.64, alpha: 0.2).setStroke()
halo.lineWidth = 3
halo.stroke()
let font = NSFont.systemFont(ofSize: 630, weight: .bold)
let rounded = NSFont(descriptor: font.fontDescriptor.withDesign(.rounded)!, size: 630)!
let shadow = NSShadow()
shadow.shadowColor = NSColor(calibratedRed: 0.13, green: 0.95, blue: 0.63, alpha: 0.38)
shadow.shadowBlurRadius = 35
shadow.shadowOffset = NSSize(width: 0, height: 0)
let attrs: [NSAttributedString.Key: Any] = [
  .font: rounded, .foregroundColor: NSColor(calibratedRed: 0.3, green: 1, blue: 0.72, alpha: 1),
  .shadow: shadow,
]
let text = NSAttributedString(string: "$", attributes: attrs)
let bounds = text.size()
text.draw(at: NSPoint(x: (1024 - bounds.width) / 2, y: (1024 - bounds.height) / 2 + 20))
// A small rising accent signals opportunity without crowding the dollar.
let accent = NSBezierPath()
accent.move(to: NSPoint(x: 739, y: 752))
accent.line(to: NSPoint(x: 801, y: 814))
accent.move(to: NSPoint(x: 757, y: 814))
accent.line(to: NSPoint(x: 801, y: 814))
accent.line(to: NSPoint(x: 801, y: 770))
accent.lineWidth = 15
accent.lineCapStyle = .round
accent.lineJoinStyle = .round
NSColor(calibratedRed: 0.75, green: 1, blue: 0.88, alpha: 1).setStroke()
accent.stroke()
NSGraphicsContext.restoreGraphicsState()
try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: output))
