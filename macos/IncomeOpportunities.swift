import Cocoa
import WebKit

func trace(_ s: String) {
  try? (s + "\n").write(
    toFile: "/tmp/income-agent-app-startup.txt", atomically: true, encoding: .utf8)
}
class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
  var window: NSWindow!
  var web: WKWebView!
  func applicationDidFinishLaunching(_ notification: Notification) {
    let menu = NSMenu()
    let item = NSMenuItem()
    menu.addItem(item)
    let appMenu = NSMenu()
    appMenu.addItem(
      withTitle: "Quit Income Opportunities", action: #selector(NSApplication.terminate(_:)),
      keyEquivalent: "q")
    item.submenu = appMenu
    let editItem = NSMenuItem()
    menu.addItem(editItem)
    let edit = NSMenu(title: "Edit")
    editItem.submenu = edit
    for (title, selector, key) in [
      ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a"),
      ("Cut", "cut:", "x"),
    ] { edit.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key) }
    NSApp.mainMenu = menu
    window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 1180, height: 820),
      styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false
    )
    window.title = "Income Opportunities"
    window.center()
    web = WKWebView(frame: window.contentView!.bounds)
    web.navigationDelegate = self
    web.uiDelegate = self
    window.contentView = web
    window.makeKeyAndOrderFront(nil)
    NSApp.activate(ignoringOtherApps: true)
    trace("web frame: \(web.frame)")
    web.loadHTMLString("<h1>Starting Income Opportunities…</h1>", baseURL: nil)
    let adjacent = Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent(
      "income-agent")
    let configuredRoot =
      Bundle.main.object(forInfoDictionaryKey: "IncomeAgentRoot") as? String ?? adjacent.path
    let installed = URL(fileURLWithPath: configuredRoot)
    let root =
      FileManager.default.fileExists(
        atPath: adjacent.appendingPathComponent("launch_dashboard.py").path) ? adjacent : installed
    DispatchQueue.global().async {
      let p = Process()
      p.executableURL = URL(
        fileURLWithPath: Bundle.main.object(forInfoDictionaryKey: "IncomeAgentPython") as? String
          ?? "/usr/bin/python3")
      p.arguments = [root.appendingPathComponent("launch_dashboard.py").path, "--no-open"]
      trace("Starting launcher: \(root.path)")
      p.standardOutput = FileHandle.nullDevice
      p.standardError = FileHandle.nullDevice
      do {
        try p.run()
        p.waitUntilExit()
        trace("Launcher exit: \(p.terminationStatus)")
        DispatchQueue.main.async {
          if p.terminationStatus == 0 {
            self.web.load(URLRequest(url: URL(string: "http://127.0.0.1:8766/")!))
          } else {
            self.showError()
          }
        }
      } catch { DispatchQueue.main.async { self.showError() } }
    }
  }
  func webView(
    _ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
    withError error: Error
  ) {
    webView.loadHTMLString(
      "<h1>Could not load the local dashboard</h1><p>" + error.localizedDescription + "</p>",
      baseURL: nil)
  }
  func showError() {
    let a = NSAlert()
    a.messageText = "Could not start Income Opportunities"
    a.informativeText =
      "Check that the income-agent project folder is available and Ubuntu is reachable."
    a.runModal()
  }
  func local(_ url: URL) -> Bool {
    return url.scheme == "http" && url.host == "127.0.0.1" && url.port == 8766
  }
  func webView(
    _ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
    decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
  ) {
    guard let url = action.request.url else {
      decisionHandler(.cancel)
      return
    }
    if local(url) || url.scheme == "blob" || url.scheme == "about" {
      decisionHandler(.allow)
    } else {
      if url.scheme == "https" { NSWorkspace.shared.open(url) }
      decisionHandler(.cancel)
    }
  }
  func webView(
    _ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
    for action: WKNavigationAction, windowFeatures: WKWindowFeatures
  ) -> WKWebView? {
    if let url = action.request.url {
      if local(url) {
        web.load(action.request)
      } else if url.scheme == "https" {
        NSWorkspace.shared.open(url)
      }
    }
    return nil
  }
  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    return true
  }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
