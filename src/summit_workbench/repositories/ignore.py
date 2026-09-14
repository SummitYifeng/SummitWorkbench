"""统一的目录忽略规则：**点开头（隐藏 / 机器目录）+ 已知机器目录名 + 下划线内部前缀**。

某目录「算不算内容」的判断原先散在三处，各自维护名单：

- :mod:`summit_workbench.repositories.project_scan`（Work 根目录扫描 → App【项目】列表）
- :mod:`summit_workbench.repositories.vault`（``wb vault check`` 的遍历）
- :mod:`summit_workbench.repositories.kb_index`（知识索引的遍历）

2026-09-14：`~/Documents/Work/.obsidian` 漏进了 App 的【项目】——`project_scan` 当时只挡
下划线前缀，不挡点开头。修一处仍会从另一处漏，故本模块是**唯一真源**；三处遍历都从这里取
判据，**不要**再各写一份名单。
"""

from __future__ import annotations

#: 没有前缀、但语义上是机器目录的名字。点开头目录（``.git`` / ``.obsidian`` /
#: ``.summit-workbench``）由 :func:`is_hidden_dirname` 兜住，这里只列「既不带点、
#: 也不是下划线前缀」的那些——目前只有库里给使用者照填的骨架模板目录 ``templates/``。
MACHINE_DIRNAMES: frozenset[str] = frozenset({"templates"})


def is_hidden_dirname(name: str) -> bool:
    """点开头目录 = 隐藏 / 机器目录（``.git``、``.obsidian``、``.summit-workbench``）。"""
    return name.startswith(".")


def is_machine_dirname(name: str) -> bool:
    """隐藏目录，或已知机器目录名（见 :data:`MACHINE_DIRNAMES`）。"""
    return is_hidden_dirname(name) or name in MACHINE_DIRNAMES


def is_internal_dirname(name: str) -> bool:
    """该目录名是否「不是内容」——Work 根目录扫描与 vault 内容遍历共用此判据。

    三种情形：

    1. 下划线前缀：``_vault``、``_signals``、``_transcripts-inbox``（系统内部目录）；
    2. 点开头：``.obsidian``、``.git``、``.summit-workbench``（隐藏 / 机器目录）；
    3. 无前缀机器目录名：``templates``（骨架模板，frontmatter 含未替换占位符）。

    ⚠️ 判据只作用于**目录名**，不作用于项目 ID 的合法性；名字里含下划线但不是前缀
    （``HIC_Logistics``）不算内部目录。
    """
    return name.startswith("_") or is_machine_dirname(name)
