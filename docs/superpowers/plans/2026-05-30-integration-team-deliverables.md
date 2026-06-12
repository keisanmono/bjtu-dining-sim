# Integration Team Deliverables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate the 20 group integration-stage team deliverables: joint test report, communication record, and system source code zip.

**Architecture:** Write Markdown sources for the two reports and source-code description, export DOCX/PDF copies with Pandoc and Chromium, then stage a clean `SRC_20组` directory for zipping. The zip excludes dependency, cache, runtime data, git metadata, and previously generated deliverables.

**Tech Stack:** Markdown, Pandoc, Chromium PDF printing, zip, officecli for inspection.

---

## File Structure

- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/20组_联调测试报告.md`
- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/20组_联调测试报告.docx`
- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/20组_联调测试报告.pdf`
- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/20组_集成阶段小组沟通交流记录.md`
- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/20组_集成阶段小组沟通交流记录.docx`
- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/20组_集成阶段小组沟通交流记录.pdf`
- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/20组_系统源代码说明.md`
- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/20组_系统源代码说明.docx`
- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/20组_系统源代码说明.pdf`
- Create: `deliverables/软件综合实训_20组_集成阶段团队材料/软件综合实训_20组_系统源代码.zip`

## Task 1: Create Report Sources

- [ ] **Step 1: Create output directory**

From the repository root, run:

```bash
mkdir -p 'deliverables/软件综合实训_20组_集成阶段团队材料'
```

Expected: directory exists.

- [ ] **Step 2: Create the joint test report Markdown**

Create `20组_联调测试报告.md` with sections: cover info, test scope, interface joint tests, system joint tests, issue handling, result summary.

- [ ] **Step 3: Create the communication record Markdown**

Create `20组_集成阶段小组沟通交流记录.md` with cover info and four dated communication records using the same field names as the course template.

- [ ] **Step 4: Create the source-code description Markdown**

Create `20组_系统源代码说明.md` with project overview, directory descriptions, startup commands, test commands, and packaging exclusions.

## Task 2: Export Documents

- [ ] **Step 1: Export each Markdown source to DOCX**

Run:

```bash
pandoc 'deliverables/软件综合实训_20组_集成阶段团队材料/20组_联调测试报告.md' -o 'deliverables/软件综合实训_20组_集成阶段团队材料/20组_联调测试报告.docx'
pandoc 'deliverables/软件综合实训_20组_集成阶段团队材料/20组_集成阶段小组沟通交流记录.md' -o 'deliverables/软件综合实训_20组_集成阶段团队材料/20组_集成阶段小组沟通交流记录.docx'
pandoc 'deliverables/软件综合实训_20组_集成阶段团队材料/20组_系统源代码说明.md' -o 'deliverables/软件综合实训_20组_集成阶段团队材料/20组_系统源代码说明.docx'
```

Expected: all three `.docx` files exist.

- [ ] **Step 2: Export each Markdown source to PDF**

Use Pandoc to HTML and Chromium `--print-to-pdf --no-pdf-header-footer` for each source.

Expected: all three `.pdf` files exist and `file` reports PDF.

## Task 3: Build Source Zip

- [ ] **Step 1: Stage clean source tree**

Create `/tmp/bjtu-dining-src/SRC_20组`, copy source directories and docs, and exclude generated runtime/dependency directories.

- [ ] **Step 2: Copy source-code description into staged source**

Copy `20组_系统源代码说明.md` and `20组_系统源代码说明.pdf` into `/tmp/bjtu-dining-src/SRC_20组/`.

- [ ] **Step 3: Create zip**

From the repository root, run:

```bash
REPO_ROOT="$(pwd)"
STAGE_ROOT="/tmp/bjtu-dining-src"
DELIVERABLE_DIR="$REPO_ROOT/deliverables/软件综合实训_20组_集成阶段团队材料"
cd "$STAGE_ROOT"
zip -r "$DELIVERABLE_DIR/软件综合实训_20组_系统源代码.zip" 'SRC_20组'
```

Expected: zip exists under the current checkout's `deliverables/软件综合实训_20组_集成阶段团队材料/` directory and contains all source, docs, tests, and the source-code description files required by the course deliverable.

## Task 4: Verify Deliverables

- [ ] **Step 1: Check generated files**

Run:

```bash
ls -lh 'deliverables/软件综合实训_20组_集成阶段团队材料'
```

Expected: team report PDFs and zip are present and non-empty.

- [ ] **Step 2: Check report text**

Run `officecli view ... text` on the two report DOCX files and confirm required headings exist.

Expected: joint test report includes `接口联调测试` and `系统联调测试`; communication record includes `沟通交流记录`.

- [ ] **Step 3: Check zip contents**

Run:

```bash
ZIP='deliverables/软件综合实训_20组_集成阶段团队材料/软件综合实训_20组_系统源代码.zip'
unzip -l "$ZIP" | sed -n '1,160p'
for required in \
  'SRC_20组/README.md' \
  'SRC_20组/backend/app/main.py' \
  'SRC_20组/backend/app/simulation.py' \
  'SRC_20组/backend/app/schemas.py' \
  'SRC_20组/backend/requirements.txt' \
  'SRC_20组/frontend/package.json' \
  'SRC_20组/frontend/src/App.vue' \
  'SRC_20组/frontend/src/layout.js' \
  'SRC_20组/tests/test_simulation.py' \
  'SRC_20组/tests/test_storage.py' \
  'SRC_20组/doc/walkthrough.md' \
  'SRC_20组/20组_系统源代码说明.md' \
  'SRC_20组/20组_系统源代码说明.pdf'
do
  unzip -l "$ZIP" "$required" >/dev/null || exit 1
done
for excluded in \
  'SRC_20组/.git/*' \
  'SRC_20组/backend/.venv/*' \
  'SRC_20组/frontend/node_modules/*' \
  'SRC_20组/data/*' \
  'SRC_20组/logs/*' \
  'SRC_20组/deliverables/*'
do
  if unzip -l "$ZIP" "$excluded" >/dev/null 2>&1; then exit 1; fi
done
```

Expected: all required entries above are present; `node_modules`, `.venv`, `.git`, `data`, `logs`, and nested `deliverables` are not present.

- [ ] **Step 4: Run verification tests**

Run:

```bash
backend/.venv/bin/python -m unittest tests.test_api tests.test_simulation tests.test_storage
cd frontend && npm test
```

Expected: backend and frontend tests pass.
