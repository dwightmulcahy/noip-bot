import importlib
import unittest


class InternalImportTests(unittest.TestCase):
    def test_dependency_free_internal_packages_import(self):
        for module_name in (
            "githubMarkdown",
            "logging_config",
            "state_store",
            "utils",
        ):
            with self.subTest(module=module_name):
                importlib.import_module(module_name)


if __name__ == "__main__":
    unittest.main()
