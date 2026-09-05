import Cocoa
import WebKit
import CoreGraphics
import Carbon

class DraggableOverlayWebView: WKWebView {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        return true
    }

    override func mouseDown(with event: NSEvent) {
        window?.performDrag(with: event)
    }
}

class OverlayDragSurfaceView: NSView {
    private var dragStartMouseLocation: CGPoint?
    private var dragStartWindowOrigin: CGPoint?

    override var acceptsFirstResponder: Bool { true }
    override var mouseDownCanMoveWindow: Bool { true }
    override var isOpaque: Bool { false }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func hitTest(_ point: NSPoint) -> NSView? {
        for sub in subviews.reversed() {
            let converted = sub.convert(point, from: self)
            if let hit = sub.hitTest(converted) { return hit }
        }
        return self
    }

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: NSCursor.openHand)
    }

    override func mouseDown(with event: NSEvent) {
        dragStartMouseLocation = NSEvent.mouseLocation
        dragStartWindowOrigin = window?.frame.origin
        NSCursor.closedHand.push()
    }

    override func mouseDragged(with event: NSEvent) {
        guard
            let startMouseLocation = dragStartMouseLocation,
            let startWindowOrigin = dragStartWindowOrigin,
            let window = window
        else { return }
        let cur = NSEvent.mouseLocation
        window.setFrameOrigin(CGPoint(
            x: startWindowOrigin.x + cur.x - startMouseLocation.x,
            y: startWindowOrigin.y + cur.y - startMouseLocation.y
        ))
    }

    override func mouseUp(with event: NSEvent) {
        dragStartMouseLocation = nil
        dragStartWindowOrigin = nil
        NSCursor.pop()
    }
}

class ResizeHandleView: NSView {
    private var dragStart: CGPoint?
    private var startFrame: CGRect?
    static let handleSize: CGFloat = 20
    static let minSize = CGSize(width: 300, height: 380)
    static let maxSize = CGSize(width: 900, height: 1100)

    override var isOpaque: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: NSCursor(image: NSCursor.arrow.image, hotSpot: .zero))
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        let local = convert(point, from: superview)
        return bounds.contains(local) ? self : nil
    }

    override func mouseDown(with event: NSEvent) {
        dragStart = NSEvent.mouseLocation
        startFrame = window?.frame
    }

    override func mouseDragged(with event: NSEvent) {
        guard let start = dragStart, let frame = startFrame, let window = window else { return }
        let cur = NSEvent.mouseLocation
        let dx = cur.x - start.x
        let dy = cur.y - start.y
        let newW = max(Self.minSize.width, min(Self.maxSize.width, frame.width + dx))
        let newH = max(Self.minSize.height, min(Self.maxSize.height, frame.height - dy))
        let newY = frame.origin.y + frame.height - newH
        window.setFrame(CGRect(x: frame.origin.x, y: newY, width: newW, height: newH), display: true)
    }

    override func mouseUp(with event: NSEvent) {
        dragStart = nil
        startFrame = nil
        if let d = window?.delegate as? AppDelegate { d.saveFrame() }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?
    var webView: WKWebView?
    var hotKeyRef: EventHotKeyRef?
    var hotKeyHandler: EventHandlerRef?
    var minimizeHotKeyRef: EventHotKeyRef?
    let frameDefaultsKey = "JarvisOverlayWindowFrame"
    let minimizedKey = "JarvisOverlayMinimized"
    var isMinimized = false
    var expandedFrame: CGRect = .zero
    let miniSize = CGSize(width: 64, height: 64)

    func applicationDidFinishLaunching(_ notification: Notification) {
        let screen = NSScreen.main ?? NSScreen.screens[0]
        let screenFrame = screen.visibleFrame

        let windowSize = CGSize(width: 500, height: 600)
        let padding: CGFloat = 50
        let defaultWindowFrame = CGRect(
            x: screenFrame.maxX - windowSize.width - padding,
            y: screenFrame.minY + padding,
            width: windowSize.width,
            height: windowSize.height
        )
        let windowFrame = savedWindowFrame(defaultFrame: defaultWindowFrame)
        expandedFrame = windowFrame

        window = NSWindow(
            contentRect: windowFrame,
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )

        guard let window = window else { return }

        window.isOpaque = false
        window.backgroundColor = NSColor.clear
        window.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.screenSaverWindow)))
        window.ignoresMouseEvents = false
        window.isMovableByWindowBackground = true
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]

        let webViewConfig = WKWebViewConfiguration()
        webViewConfig.defaultWebpagePreferences.allowsContentJavaScript = true
        let handler = ScriptMessageHandler(delegate: self)
        webViewConfig.userContentController.add(handler, name: "jarvisOverlay")

        let contentView = OverlayDragSurfaceView(frame: CGRect(origin: .zero, size: windowFrame.size))
        contentView.wantsLayer = true
        contentView.layer?.isOpaque = false
        contentView.layer?.backgroundColor = NSColor.clear.cgColor
        contentView.autoresizesSubviews = true
        window.contentView = contentView

        webView = DraggableOverlayWebView(
            frame: contentView.bounds,
            configuration: webViewConfig
        )
        guard let webView = webView else { return }

        webView.autoresizingMask = [.width, .height]
        webView.wantsLayer = true
        webView.layer?.isOpaque = false
        webView.layer?.backgroundColor = NSColor.clear.cgColor

        if #available(macOS 12.0, *) {
            webView.underPageBackgroundColor = .clear
        }
        webView.setValue(false, forKey: "drawsBackground")

        contentView.addSubview(webView)

        let resizeHandle = ResizeHandleView(frame: CGRect(
            x: contentView.bounds.width - ResizeHandleView.handleSize,
            y: 0,
            width: ResizeHandleView.handleSize,
            height: ResizeHandleView.handleSize
        ))
        resizeHandle.autoresizingMask = [.minXMargin, .maxYMargin]
        contentView.addSubview(resizeHandle)

        loadOverlayHTML()
        window.orderFrontRegardless()
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(windowDidMove(_:)),
            name: NSWindow.didMoveNotification,
            object: window
        )
        registerGlobalHotKey()

        if UserDefaults.standard.bool(forKey: minimizedKey) {
            toggleMinimize()
        }
    }

    func savedWindowFrame(defaultFrame: CGRect) -> CGRect {
        guard let frameString = UserDefaults.standard.string(forKey: frameDefaultsKey) else {
            return defaultFrame
        }
        let frame = NSRectFromString(frameString)
        guard
            frame.width > 0,
            frame.height > 0,
            NSScreen.screens.contains(where: { $0.visibleFrame.intersects(frame) })
        else {
            return defaultFrame
        }
        return frame
    }

    func saveFrame() {
        guard let frame = window?.frame else { return }
        if !isMinimized {
            expandedFrame = frame
        }
        UserDefaults.standard.set(NSStringFromRect(expandedFrame), forKey: frameDefaultsKey)
    }

    @objc func windowDidMove(_ notification: Notification) {
        saveFrame()
    }

    func toggleMinimize() {
        guard let window = window else { return }

        if isMinimized {
            isMinimized = false
            UserDefaults.standard.set(false, forKey: minimizedKey)
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.3
                ctx.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                window.animator().setFrame(expandedFrame, display: true)
                window.animator().alphaValue = 1.0
            }
            webView?.evaluateJavaScript("window.jarvisSetMinimized && window.jarvisSetMinimized(false);", completionHandler: nil)
        } else {
            expandedFrame = window.frame
            UserDefaults.standard.set(NSStringFromRect(expandedFrame), forKey: frameDefaultsKey)
            isMinimized = true
            UserDefaults.standard.set(true, forKey: minimizedKey)

            let screen = window.screen ?? NSScreen.main ?? NSScreen.screens[0]
            let visFrame = screen.visibleFrame
            let miniFrame = CGRect(
                x: visFrame.maxX - miniSize.width - 16,
                y: visFrame.minY + 16,
                width: miniSize.width,
                height: miniSize.height
            )
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.3
                ctx.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                window.animator().setFrame(miniFrame, display: true)
            }
            webView?.evaluateJavaScript("window.jarvisSetMinimized && window.jarvisSetMinimized(true);", completionHandler: nil)
        }
    }

    func loadOverlayHTML() {
        if
            let overlayURLString = ProcessInfo.processInfo.environment["JARVIS_OVERLAY_URL"],
            let overlayURL = URL(string: overlayURLString)
        {
            webView?.load(URLRequest(url: overlayURL))
            return
        }

        guard
            let webView = webView,
            let resourcesURL = Bundle.main.resourceURL,
            let overlayURL = Bundle.main.url(forResource: "overlay", withExtension: "html")
        else {
            webView?.loadHTMLString(
                "<!doctype html><meta charset=\"utf-8\"><body style=\"background:transparent\"></body>",
                baseURL: Bundle.main.resourceURL
            )
            return
        }

        do {
            let htmlContent = try String(contentsOf: overlayURL, encoding: .utf8)
            webView.loadHTMLString(htmlContent, baseURL: resourcesURL)
        } catch {
            NSLog("JARVIS overlay failed to load HTML: \(error.localizedDescription)")
            webView.loadHTMLString(
                "<!doctype html><meta charset=\"utf-8\"><body style=\"background:transparent\"></body>",
                baseURL: resourcesURL
            )
        }
    }

    func registerGlobalHotKey() {
        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )

        let callback: EventHandlerUPP = { _, event, userData in
            guard let userData = userData, let event = event else { return noErr }
            var hotKeyID = EventHotKeyID()
            GetEventParameter(event, EventParamName(kEventParamDirectObject),
                              EventParamType(typeEventHotKeyID), nil,
                              MemoryLayout<EventHotKeyID>.size, nil, &hotKeyID)
            let delegate = Unmanaged<AppDelegate>.fromOpaque(userData).takeUnretainedValue()
            DispatchQueue.main.async {
                if hotKeyID.id == 2 {
                    delegate.handleMinimizeHotKey()
                } else {
                    delegate.handleHotKey()
                }
            }
            return noErr
        }

        let handlerStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            callback,
            1,
            &eventType,
            Unmanaged.passUnretained(self).toOpaque(),
            &hotKeyHandler
        )

        guard handlerStatus == noErr else {
            NSLog("JARVIS overlay hotkey handler registration failed: \(handlerStatus)")
            return
        }

        let hotKeyID = EventHotKeyID(signature: fourCharCode("JRVS"), id: 1)
        let hotKeyStatus = RegisterEventHotKey(
            UInt32(kVK_ANSI_J),
            UInt32(controlKey | optionKey),
            hotKeyID,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )

        if hotKeyStatus != noErr {
            NSLog("JARVIS overlay hotkey registration failed: \(hotKeyStatus)")
        }

        let minimizeKeyID = EventHotKeyID(signature: fourCharCode("JRVS"), id: 2)
        let minimizeStatus = RegisterEventHotKey(
            UInt32(kVK_ANSI_M),
            UInt32(controlKey | optionKey),
            minimizeKeyID,
            GetApplicationEventTarget(),
            0,
            &minimizeHotKeyRef
        )
        if minimizeStatus != noErr {
            NSLog("JARVIS overlay minimize hotkey registration failed: \(minimizeStatus)")
        }
    }

    func unregisterGlobalHotKey() {
        if let hotKeyRef = hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
            self.hotKeyRef = nil
        }
        if let minimizeHotKeyRef = minimizeHotKeyRef {
            UnregisterEventHotKey(minimizeHotKeyRef)
            self.minimizeHotKeyRef = nil
        }
        if let hotKeyHandler = hotKeyHandler {
            RemoveEventHandler(hotKeyHandler)
            self.hotKeyHandler = nil
        }
    }

    func handleHotKey() {
        if isMinimized {
            toggleMinimize()
        }
        webView?.evaluateJavaScript(
            "window.jarvisActivateVoice && window.jarvisActivateVoice();",
            completionHandler: nil
        )
    }

    func handleMinimizeHotKey() {
        toggleMinimize()
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let window = window {
            UserDefaults.standard.set(NSStringFromRect(window.frame), forKey: frameDefaultsKey)
        }
        NotificationCenter.default.removeObserver(self)
        unregisterGlobalHotKey()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool {
        return true
    }
}

class ScriptMessageHandler: NSObject, WKScriptMessageHandler {
    weak var delegate: AppDelegate?
    init(delegate: AppDelegate) { self.delegate = delegate; super.init() }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? String else { return }
        if body == "toggleMinimize" {
            delegate?.toggleMinimize()
        }
    }
}

func fourCharCode(_ string: String) -> OSType {
    var result: UInt32 = 0
    for scalar in string.unicodeScalars.prefix(4) {
        result = (result << 8) + UInt32(scalar.value)
    }
    return OSType(result)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
