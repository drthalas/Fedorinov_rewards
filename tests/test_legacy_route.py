import unittest

from backend.app.main import app


class LegacyRouteTests(unittest.TestCase):
    def test_legacy_get_route_is_registered(self) -> None:
        methods = [
            route.methods
            for route in app.routes
            if getattr(route, "path", None) == "/legacy" and "GET" in getattr(route, "methods", set())
        ]
        self.assertTrue(methods)

    def test_legacy_head_route_is_registered(self) -> None:
        methods = [
            route.methods
            for route in app.routes
            if getattr(route, "path", None) == "/legacy" and "HEAD" in getattr(route, "methods", set())
        ]
        self.assertTrue(methods)


if __name__ == "__main__":
    unittest.main()
