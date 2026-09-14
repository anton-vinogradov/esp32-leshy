#pragma once

#include <cstdint>

namespace leshy1::ui {

enum class WifiNetworkPage : std::uint8_t {
    Summary, Radar, Actions, Information, Identity, Protection, Radio, Observed,
    ListenName,
};
enum class WifiNetworkKey : std::uint8_t { Up, Down, Left, Right, Ok };
inline const char* wifiNetworkPageName(WifiNetworkPage page) {
    switch (page) {
        case WifiNetworkPage::Summary: return "summary";
        case WifiNetworkPage::Radar: return "radar";
        case WifiNetworkPage::Actions: return "actions";
        case WifiNetworkPage::Information: return "information";
        case WifiNetworkPage::Identity: return "identity";
        case WifiNetworkPage::Protection: return "protection";
        case WifiNetworkPage::Radio: return "radio";
        case WifiNetworkPage::Observed: return "observed";
        case WifiNetworkPage::ListenName: return "listen_name";
    }
    return "unknown";
}
enum class WifiNetworkIntent : std::uint8_t { None, Changed, Exit, Password, ListenName };

// Pure navigation: traversing a page cannot start a capture or transmit.
class WifiNetworkNavigation final {
  public:
    void reset() { page_ = WifiNetworkPage::Summary; selection_ = 0; }
    WifiNetworkPage page() const { return page_; }
    std::uint8_t selection() const { return selection_; }
    std::uint8_t rowCount() const {
        return page_ == WifiNetworkPage::Actions ? 3U :
            (page_ == WifiNetworkPage::Information ? 4U : 0U);
    }
    WifiNetworkIntent handle(WifiNetworkKey key) {
        using Page = WifiNetworkPage;
        using Key = WifiNetworkKey;
        using Intent = WifiNetworkIntent;
        if (key == Key::Left) {
            switch (page_) {
                case Page::Summary: return Intent::Exit;
                case Page::Actions:
                case Page::Radar: page_ = Page::Summary; break;
                case Page::Information: page_ = Page::Actions; selection_ = 2; break;
                case Page::ListenName: page_ = Page::Identity; break;
                case Page::Protection:
                    page_ = protectionParent_;
                    selection_ = page_ == Page::Information ? 1U : 0U; break;
                default:
                    selection_ = page_ == Page::Identity ? 0U :
                        (page_ == Page::Radio ? 2U : 3U);
                    page_ = Page::Information; break;
            }
            return Intent::Changed;
        }
        if (key == Key::Up && rowCount() != 0U && selection_ > 0U) {
            --selection_; return Intent::Changed;
        }
        if (key == Key::Down && selection_ + 1U < rowCount()) {
            ++selection_; return Intent::Changed;
        }
        if (page_ == Page::Summary && key == Key::Ok) {
            page_ = Page::Radar; return Intent::Changed;
        }
        if ((page_ == Page::Summary || page_ == Page::Radar) && key == Key::Right) {
            page_ = Page::Actions; selection_ = 0; return Intent::Changed;
        }
        if (key != Key::Ok && key != Key::Right) return Intent::None;
        if (page_ == Page::Identity) {
            page_ = Page::ListenName; return Intent::Changed;
        }
        if (page_ == Page::ListenName && key == Key::Ok) return Intent::ListenName;
        if (page_ == Page::Actions) {
            if (selection_ == 1U) return Intent::Password;
            protectionParent_ = Page::Actions;
            page_ = selection_ == 0U ? Page::Protection : Page::Information;
            selection_ = 0;
            return Intent::Changed;
        }
        if (page_ == Page::Information) {
            constexpr Page pages[] = {
                Page::Identity, Page::Protection, Page::Radio, Page::Observed};
            protectionParent_ = Page::Information;
            page_ = pages[selection_];
            return Intent::Changed;
        }
        return Intent::None;
    }
  private:
    WifiNetworkPage page_ = WifiNetworkPage::Summary;
    WifiNetworkPage protectionParent_ = WifiNetworkPage::Actions;
    std::uint8_t selection_ = 0;
};

}  // namespace leshy1::ui
