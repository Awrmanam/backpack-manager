import unittest

from backpack_manager.web import HTML


class WebUiTests(unittest.TestCase):
    def test_quota_cards_show_clear_usage_copy(self):
        self.assertIn("مصرف دانلود", HTML)
        self.assertIn("باقی‌مانده", HTML)
        self.assertIn("سقف دانلود", HTML)
        self.assertIn("نامحدود", HTML)
        self.assertIn("آپلود رایگان", HTML)

    def test_many_ports_are_collapsed_but_counted_as_a_tunnel_group(self):
        self.assertIn("expandedPortCount", HTML)
        self.assertIn("مشاهده پورت‌ها", HTML)
        self.assertIn("مصرف همه پورت‌های هر Tunnel", HTML)

    def test_expiry_display_is_normalized(self):
        self.assertIn("formatDate", HTML)
        self.assertIn("روز باقی‌مانده", HTML)
        self.assertIn("بدون انقضا", HTML)


if __name__ == "__main__":
    unittest.main()
