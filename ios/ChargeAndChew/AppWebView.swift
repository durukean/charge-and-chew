import WebKit
import ObjectiveC

/// WKWebView without the ▲ ▼ ✓ keyboard accessory bar.
///
/// That bar is the single most recognisable sign of a web page inside an app, and WebKit
/// offers no public switch for it. The technique below is the one Capacitor, Cordova and
/// Flutter's webview all ship: find WebKit's content view inside the scroll view, give it a
/// runtime subclass whose `inputAccessoryView` returns nil, and swap the class. No private
/// selector is named; nothing is called that is not public API.
final class AppWebView: WKWebView {

    override func didMoveToWindow() {
        super.didMoveToWindow()
        removeInputAccessory()
    }

    private func removeInputAccessory() {
        guard let target = scrollView.subviews.first(where: {
            String(describing: type(of: $0)).hasPrefix("WKContent")
        }) else { return }
        let name = "\(String(describing: type(of: target)))_NoAccessory"
        if let cls = NSClassFromString(name) {
            object_setClass(target, cls); return
        }
        guard let cls = objc_allocateClassPair(object_getClass(target), name, 0) else { return }
        let sel = #selector(getter: UIResponder.inputAccessoryView)
        let imp = imp_implementationWithBlock({ (_: AnyObject) -> UIView? in nil } as @convention(block) (AnyObject) -> UIView?)
        if let method = class_getInstanceMethod(object_getClass(target), sel) {
            class_addMethod(cls, sel, imp, method_getTypeEncoding(method))
        }
        objc_registerClassPair(cls)
        object_setClass(target, cls)
    }
}
