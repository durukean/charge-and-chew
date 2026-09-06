import UIKit

/// Deliberately NOT using a UIScene manifest.
///
/// A scene manifest resolves its delegate by STRING through the Objective-C runtime
/// (`ChargeAndChew.SceneDelegate`), and under Xcode 26's debug-dylib layout that lookup
/// silently failed here: the app launched, stayed running, connected no scene, and rendered
/// a black window with not one line of our code ever executing. Nothing in the log said so.
/// This app has exactly one window, so the classic AppDelegate window costs nothing and
/// removes a whole class of failure that is invisible when it happens.
@main
final class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ app: UIApplication,
                     didFinishLaunchingWithOptions opts: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = WebViewController()
        window.makeKeyAndVisible()
        self.window = window
        return true
    }
}
