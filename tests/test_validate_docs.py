import tempfile
import unittest
from pathlib import Path

from scripts.validate_docs import validate_document, validate_repository


VALID_LESSON = """---
title: 示例课程
slug: sample-lesson
module: traditional-solutions
stage: discover
type: core
difficulty: beginner
duration: 30m
prerequisites:
  - none
outcomes:
  - 解释示例概念
last_reviewed: 2026-10-16
---

# 示例课程

## 为什么需要学习
内容。
## 学习目标
内容。
## 前置知识
内容。
## 业务场景
内容。
## 核心概念
内容。
## 工作原理
内容。
## 架构与选型
内容。
## 最小示例
内容。
## 动手实验
内容。
## 常见错误与排查
内容。
## 安全与生产注意事项
内容。
## 本课总结
内容。
## 思考题
内容。
## 小测
内容。
## 答案与解析
内容。
## 延伸阅读与下一课
内容。
"""


class ValidatorTests(unittest.TestCase):
    def make_docs(self, files: dict[str, str]) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        root = Path(temporary_directory.name) / "docs"
        root.mkdir()
        for relative_path, content in files.items():
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        return temporary_directory, root

    def test_valid_core_lesson_has_no_issues(self):
        temporary_directory, root = self.make_docs({"lesson.md": VALID_LESSON})
        self.addCleanup(temporary_directory.cleanup)

        self.assertEqual(validate_document(root / "lesson.md", root), [])

    def test_missing_front_matter_reports_metadata_error(self):
        temporary_directory, root = self.make_docs({"lesson.md": "# 没有元数据\n"})
        self.addCleanup(temporary_directory.cleanup)

        codes = [issue.code for issue in validate_document(root / "lesson.md", root)]

        self.assertIn("metadata", codes)

    def test_duplicate_slugs_report_duplicate_slug(self):
        second_lesson = VALID_LESSON.replace("title: 示例课程", "title: 第二课", 1)
        temporary_directory, root = self.make_docs(
            {"first.md": VALID_LESSON, "second.md": second_lesson}
        )
        self.addCleanup(temporary_directory.cleanup)

        issues = validate_repository(root)

        self.assertEqual([issue.code for issue in issues].count("duplicate-slug"), 2)

    def test_broken_relative_file_link_reports_broken_link(self):
        lesson = VALID_LESSON.replace("内容。\n## 学习目标", "[缺失课程](missing.md)\n## 学习目标", 1)
        temporary_directory, root = self.make_docs({"lesson.md": lesson})
        self.addCleanup(temporary_directory.cleanup)

        codes = [issue.code for issue in validate_document(root / "lesson.md", root)]

        self.assertIn("broken-link", codes)

    def test_broken_local_anchor_reports_broken_anchor(self):
        lesson = VALID_LESSON.replace("内容。\n## 学习目标", "[跳转](#不存在)\n## 学习目标", 1)
        temporary_directory, root = self.make_docs({"lesson.md": lesson})
        self.addCleanup(temporary_directory.cleanup)

        codes = [issue.code for issue in validate_document(root / "lesson.md", root)]

        self.assertIn("broken-anchor", codes)

    def test_chinese_heading_anchor_is_resolved(self):
        lesson = VALID_LESSON.replace("内容。\n## 学习目标", "[跳转](#学习目标)\n## 学习目标", 1)
        temporary_directory, root = self.make_docs({"lesson.md": lesson})
        self.addCleanup(temporary_directory.cleanup)

        codes = [issue.code for issue in validate_document(root / "lesson.md", root)]

        self.assertNotIn("broken-anchor", codes)

    def test_template_directory_is_ignored(self):
        temporary_directory, root = self.make_docs(
            {"lesson.md": VALID_LESSON, "_templates/lesson-template.md": "{{ title }}"}
        )
        self.addCleanup(temporary_directory.cleanup)

        self.assertEqual(validate_repository(root), [])

    def test_placeholder_review_date_reports_invalid_review_date(self):
        lesson = VALID_LESSON.replace("2026-10-16", "YYYY-MM-DD")
        temporary_directory, root = self.make_docs({"lesson.md": lesson})
        self.addCleanup(temporary_directory.cleanup)

        codes = [issue.code for issue in validate_document(root / "lesson.md", root)]

        self.assertIn("invalid-review-date", codes)

    def test_missing_required_core_section_reports_missing_section(self):
        lesson = VALID_LESSON.replace("## 安全与生产注意事项\n内容。\n", "")
        temporary_directory, root = self.make_docs({"lesson.md": lesson})
        self.addCleanup(temporary_directory.cleanup)

        issues = validate_document(root / "lesson.md", root)

        self.assertTrue(
            any(
                issue.code == "missing-section" and "安全与生产注意事项" in issue.message
                for issue in issues
            )
        )


class CourseRepositoryTests(unittest.TestCase):
    def test_course_entry_files_exist_and_readme_links_to_start(self):
        repository_root = Path(__file__).resolve().parents[1]
        expected_files = (
            "README.md",
            "docs/00-start-here/00-course-introduction.md",
            "docs/00-start-here/01-learning-guide.md",
            "docs/00-start-here/02-environment-setup.md",
            "docs/00-start-here/03-solution-lifecycle.md",
            "docs/00-start-here/04-knowledge-map.md",
            "docs/reference/glossary.md",
            "docs/reference/technology-index.md",
            "docs/reference/troubleshooting-index.md",
            "docs/reference/architecture-deliverables.md",
            "docs/reference/further-learning.md",
        )

        for relative_path in expected_files:
            self.assertTrue((repository_root / relative_path).exists(), relative_path)
        readme = (repository_root / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/00-start-here/00-course-introduction.md", readme)

    def test_every_published_unit_has_overview_and_stage_assessment(self):
        repository_root = Path(__file__).resolve().parents[1]
        module_root = repository_root / "docs/01-traditional-solutions"
        unit_directories = sorted(path for path in module_root.iterdir() if path.is_dir())

        self.assertTrue(unit_directories, "expected at least one published unit")
        for unit_directory in unit_directories:
            names = {path.name for path in unit_directory.glob("*.md")}
            self.assertIn("00-overview.md", names, unit_directory.name)
            assessments = [name for name in names if name.endswith("-stage-assessment.md")]
            self.assertEqual(len(assessments), 1, unit_directory.name)


if __name__ == "__main__":
    unittest.main()
