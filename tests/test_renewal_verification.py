import ast
import pathlib
import unittest


def load_verifier():
    source_path = pathlib.Path(__file__).parents[1] / "noip_renew" / "noip_renew.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "renewal_is_verified"
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {}
    exec(compile(module, str(source_path), "exec"), namespace)
    return namespace["renewal_is_verified"]


class RenewalVerificationTests(unittest.TestCase):
    verifier = staticmethod(load_verifier())

    def test_requires_button_to_disappear(self):
        self.assertFalse(self.verifier([object()], "old", "new"))

    def test_requires_timestamp_to_change(self):
        self.assertFalse(self.verifier([], "same", "same"))

    def test_accepts_both_success_signals(self):
        self.assertTrue(self.verifier([], "old", "new"))


if __name__ == "__main__":
    unittest.main()
