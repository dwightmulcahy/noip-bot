import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class WorkflowTests(unittest.TestCase):
    def test_ci_verifies_pushes_and_pull_requests(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn('branches: ["**"]', workflow)
        self.assertIn("pull_request:", workflow)
        self.assertIn("workflow_call:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("ruff check .", workflow)
        self.assertIn("ruff format --check .", workflow)
        self.assertIn("mypy", workflow)
        self.assertIn('python-version: ["3.12", "3.14"]', workflow)
        self.assertIn("python-version: ${{ matrix.python-version }}", workflow)
        self.assertIn(
            "dwightmulcahy/repo-template/.github/workflows/reusable-python-ci.yml@",
            workflow,
        )
        self.assertRegex(workflow, r"docker/build-push-action@[0-9a-f]{40}")
        self.assertIn("scripts/container_smoke_test.sh", workflow)
        self.assertIn("aquasecurity/trivy-action@", workflow)
        self.assertIn("severity: CRITICAL,HIGH", workflow)

    def test_release_publishes_multi_arch_docker_hub_image(self):
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        self.assertIn('tags:\n      - "*.*.*"', workflow)
        self.assertIn("github.ref_name", workflow)
        self.assertIn("refs/heads/release:refs/remotes/origin/release", workflow)
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("IMAGE_NAME: dwightmulcahy/noip-bot", workflow)
        self.assertIn(
            "uses: dwightmulcahy/repo-template/.github/workflows/reusable-docker-publish.yml@",
            workflow,
        )
        self.assertIn("APP_VERSION=${{ github.ref_name }}", workflow)
        self.assertIn(
            "is_latest: ${{ needs.preflight.outputs.is_latest == 'true' }}", workflow
        )
        self.assertIn("secrets.DOCKERHUB_USERNAME", workflow)
        self.assertIn("secrets.DOCKERHUB_TOKEN", workflow)
        self.assertIn("group: docker-release", workflow)
        self.assertNotIn("group: docker-release-${{ github.ref_name }}", workflow)
        self.assertIn("id: release_version", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("validate:", workflow)
        self.assertIn("uses: ./.github/workflows/ci.yml", workflow)
        self.assertIn("needs: [preflight, validate]", workflow)
        self.assertNotIn("Build local release candidate", workflow)
        self.assertIn("github-release:", workflow)
        self.assertIn("needs: [preflight, publish]", workflow)
        self.assertIn(
            "dwightmulcahy/repo-template/.github/actions/release-notes@", workflow
        )
        self.assertIn('gh release create "${RELEASE_TAG}"', workflow)
        self.assertIn('gh release edit "${RELEASE_TAG}"', workflow)
        self.assertIn('latest_flag="--latest=false"', workflow)
        self.assertIn("github-release:", workflow)
        self.assertIn("      contents: write", workflow)

    def test_all_external_actions_are_pinned_to_full_shas(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            workflow = path.read_text()
            references = re.findall(r"uses:\s+([^\s#]+)", workflow)
            for reference in references:
                if reference.startswith("./"):
                    continue
                with self.subTest(workflow=path.name, reference=reference):
                    self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$")

    def test_dependabot_covers_supported_ecosystems(self):
        config = (ROOT / ".github" / "dependabot.yml").read_text()
        self.assertIn("package-ecosystem: pip", config)
        self.assertIn("package-ecosystem: docker", config)
        self.assertIn("package-ecosystem: github-actions", config)
        self.assertIn("package-ecosystem: docker-compose", config)
        self.assertEqual(config.count("day: monday"), 4)
        self.assertIn('prefix: "build(deps)"', config)
        self.assertIn('prefix: "build(docker)"', config)
        self.assertIn('prefix: "build(compose)"', config)
        self.assertIn('prefix: "ci(deps)"', config)


if __name__ == "__main__":
    unittest.main()
