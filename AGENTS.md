# JudgmentOS - Agent Working Rules

**Last Updated**: 2026-06-12  
**Purpose**: 强制执行的代码修改和调试规范，防止低质量修复和隐性 bug。

---

## Rule 1 — Think Before Coding
No silent assumptions. State what you're assuming. Surface tradeoffs. Ask before guessing. Push back when a simpler approach exists.


---

## Rule 2 — Simplicity First
Minimum code that solves the problem. No speculative features. No abstractions for single-use code. If a senior engineer would call it overcomplicated — simplify.


---

## Rule 3 — Surgical Changes
Touch only what you must. Don't "improve" adjacent code, comments, or formatting. Don't refactor what isn't broken. Match existing style.

---

## Rule 4 — Goal-Driven Execution
Define success criteria. Loop until verified. Don't tell the user what steps to follow, tell them what success looks like and let them decide.


---

## Rule 5 — Use the model only for judgment calls
Use LLM for: classification, drafting, summarization, extraction from unstructured text.  
Do NOT use LLM for: routing, retries, status-code handling, deterministic transforms.  
If logic can be written in Python, don't ask LLM.


---

## Rule 6 — Token budgets are not advisory


---

## Rule 7 — Surface conflicts, don't average them
If two existing patterns in the codebase contradict, don't blend them.  
Pick one (the more recent / more tested), explain why, and flag the other for cleanup.  
"Average" code that satisfies both rules is the worst code.

---

## Rule 8 — Read before you write
Before adding code in a file, read the file's exports, the immediate caller, and any obvious shared utilities.  
If you don't understand why existing code is structured the way it is, ask before adding to it.  
"Looks orthogonal to me" is the most dangerous phrase in this codebase.


---

## Rule 9 — Tests verify intent, not just behavior
Every test must encode WHY the behavior matters, not just WHAT it does.  
A test like `assert persona.id == "test"` is worthless if you hardcoded the ID.  
If you can't write a test that would fail when business logic changes, the function is wrong.

---

## Rule 10 — Checkpoint after every significant step
After completing each step in a multi-step task: summarize what was done, what's verified, what's left.  
Don't continue from a state you can't describe back to me.  
If you lose track, stop and restate.

---

## Rule 11 — Match the codebase's conventions, even if you disagree
If the codebase uses snake_case and you'd prefer camelCase: snake_case.  
Disagreement is a separate conversation. Inside the codebase, conformance > taste.  
If you genuinely think the convention is harmful, surface it. Don't fork it silently.


---

## Rule 12 — Fail loud
If you can't be sure something worked, say so explicitly.  
"Module implemented" is wrong if you didn't test it.  
"Tests pass" is wrong if you skipped any.  
Default to surfacing uncertainty, not hiding it.



## 核心设计原则（最重要）


---

## 违规处理

如果发现自己违反了上述规则：
1. 立刻停止当前操作
2. 告诉用户"我刚才违反了 Rule X，需要重新来"
3. 回到正确的流程

如果用户发现你违反了规则：
1. 承认错误
2. 解释为什么会违反（是理解错了还是忘记了）
3. 重新按规则执行

---

**这个文件是活的，不是死的。发现规则不够用，立刻补充。**

---
