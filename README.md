# 太易（YI）

太易帮助 Agent 完成开发和文字任务，同时减少重复实现、防御性包裹、失效说明和无效审查。它由一个可加载的技能和一个暂存预算工具组成：Agent 负责理解、修改和精简，工具负责确定性增长检查。

## 实际使用

让 Agent 读取 [SKILL.md](SKILL.md)，然后直接给任务。例如：

- “使用太易，为这个数据分析项目建立可运行入口和必要开发约定。”
- “使用太易精简这个项目，合并薄层和重复校验，保留当前功能。”
- “使用太易修改这份说明，删掉黑话和重复辩护，保留技术含义与事实。”

支持 Agent Skills 的客户端可把此仓库放到其技能目录，技能目录名使用 `yi`；按客户端规则验证是否被发现。直接读取 SKILL.md 也可使用。预算命令不会安装技能或修改用户级设置。

[初始化](initialize.txt)、[存量减负](retrofit.txt)和[文字处理](writing.txt)按任务读取，不全部放进项目常驻规则。项目只保留必要约定和真实运行方式，不复制研究报告。文字处理保留专业术语、数值对应及必要限制；不把禁词表当成语义检查器。

## 一次启用常驻约束

对 Agent 说：“使用太易，让当前项目以后持续遵守开发、文字和增长约束。”技能会按以下步骤完成接入。无需后台守护进程；规则随项目保存，hook 在每次普通提交时执行。

以下命令从目标项目运行，先将 `YI` 设为太易仓库的绝对路径：

```sh
python3 -m venv .cache/ratchet-env
.cache/ratchet-env/bin/python -m pip install ratchet-size==0.2.3
.cache/ratchet-env/bin/python "$YI/scripts/resident.py" enable
```

启用器把 YI 约定追加到带标记的项目规则区块，优先使用已有 `AGENTS.override.md`，否则使用 `AGENTS.md`；已有 `CLAUDE.md` 时也接入。它复制预算工具到 `.yi/yi.py`，将旧 pre-commit 原样备份并串联执行，不覆盖其他 hook。不改用户级配置，也不自动暂存或提交。

**首次基线还没有暂存时，enable 返回 1 并说明缺什么，这是已安装、尚未就绪。** Agent 应继续审阅并明确暂存实际项目文件、`.yi/yi.py` 和被更新的规则，然后初始化预算并暂存配置：

```sh
# 先 git add 明确选择的项目文件和上述安装文件；不要盲目 add -A。
.cache/ratchet-env/bin/python .yi/yi.py init
# 核对分组与 outside_budget 后：
git add .ratchet.json
.cache/ratchet-env/bin/python "$YI/scripts/resident.py" status
```

已有预算时跳过 init，保留原统计范围；安装引起的增长按授权记录，不重新初始化绕过额度。`status` 核对安装文件、规则区块、hook、依赖和暂存配置是否存在；预算是否通过另用 `.yi/yi.py check`。启用完成后开始新 Agent 会话。不同客户端加载行为有差异，启用不会宣称已验证客户端理解或语义遵循。

```sh
# 检查持久安装；修改或丢失会明确报告
.cache/ratchet-env/bin/python "$YI/scripts/resident.py" status
# 撤销 YI 安装，恢复旧 hook；保留预算与依赖环境
.cache/ratchet-env/bin/python "$YI/scripts/resident.py" disable
```

重复 enable 不重复添加规则。若安装内容被用户改过，disable 拒绝静默删除，先保留现场；规则区块外的用户补充会留下。新克隆缺少本地 hook，可准备环境后再 enable，已有相同安装文件会复用。链接规则文件、已存在但不同的工具、仓库外共享 hooksPath 和 linked worktree 需要明确集成，启用器在写入前拒绝猜测处理。当前启用器面向普通 Git 检出与 POSIX shell。

这是持久的项目级约束：Git 负责预算阻断，Agent 负责语义判断。去黑话、模块职责与重复防御不由行数工具裁定。没有提交的编辑不会触发 Git hook；远端保护仍需在托管服务配置。

## 可执行预算

需要 Python 3.10+、Git；下面命令从目标项目根目录运行，`YI` 表示本仓库的绝对路径：

```sh
python3 -m venv .cache/ratchet-env
.cache/ratchet-env/bin/python -m pip install ratchet-size==0.2.3
# 先审阅并暂存准备纳入基线的实际项目文件；不要盲目 git add -A。
.cache/ratchet-env/bin/python "$YI/scripts/yi.py" init
# 审阅输出中的分组及 outside_budget，再暂存 .ratchet.json。
.cache/ratchet-env/bin/python "$YI/scripts/yi.py" check
.cache/ratchet-env/bin/python "$YI/scripts/yi.py" budget
```

源码、测试、说明和维护文件默认分组；初始化仅从暂存 Git blob 计数，未暂存和未跟踪文件不会变成额度。默认分组与 2,000 行文件上限是起点，应按项目职责校准。未匹配文件会列出，不能将其误称为已覆盖。配置范围变化默认拒绝；经用户授权后，把实际 groups 的 SHA-256 写入新增 grant 的 `scope_sha256` 字段，检查仅接受该范围。`--accept-policy-change` 只用于显式审阅时的本地检查，不供 CI 全局放行。数值上限增长仍需 Ratchet grant 记录；记录不等于人员认证。

把同一工具用于本地 Git 提交（POSIX shell）：

```sh
mkdir -p .yi
cp "$YI/scripts/yi.py" .yi/yi.py
# 将 .yi/yi.py 一并审阅、暂存，再建立初始基线。
# 无现有 hook 时安装；已有 hook 时合并调用，不能覆盖。
cp "$YI/templates/pre-commit" .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

先复制、暂存工具再初始化，可将工具自身计入维护预算。若已建立预算，工具的引入属于需要记录的增长。现有仓库先读 [预算方案](structure-and-budget.md)，不要重建已提交的基线。

清理完成且验证通过后，暂存清理内容，再执行 `yi.py tighten`；它将收紧后的配置写回工作区，随后与清理一起暂存。工作区配置尚未暂存时拒绝覆盖。CI 在干净检出后运行同一工具，可用 `--base <基线提交>` 明确比较起点；push 后检查不会撤销已发生的推送。

本地 hook 可以绕过；有权限修改工具、批准日志和配置的人仍能改变规则。YI 不提供人员认证或远端保护。LFS 指针、符号链接和子模块落入受限范围时会拒绝计量，需单独确定其实际内容如何管理。

## 验证与研究

在 YI 仓库安装相同 Ratchet 环境后运行：

```sh
.cache/ratchet-env/bin/python -m unittest discover -s tests -v
```

测试使用临时 Git 仓库，覆盖初始化、增长、批准、精简、回涨以及未暂存材料隔离。[文字案例](examples/writing.md)提供编辑结果和应保持的事实关系，供实际任务评价使用；它不是自动语义等价测试。

[研究依据](research.md)解释取舍，[预算方案](structure-and-budget.md)说明计量与执行边界。[verification.json](verification.json)记录本发布版本的验证范围；回归通过不证明长期跨项目收益。

欢迎提交实际任务、重复实现或文字改坏含义的案例，说明模型、工具、输入、结果及成本。贡献应改善行为、表达或维护成本，而不是增加一套相似检查。

## 本仓库的实际接入

YI 自身的预算记录在 `.ratchet.json`，本地提交入口为 `.githooks/pre-commit`，CI 同时运行测试与预算检查。新克隆不会自动安装 Git hook；安装上述环境后，在没有现存 pre-commit 时链接 `.git/hooks/pre-commit` 到 `../../.githooks/pre-commit`。已有 hook 应合并调用。CI 配置不自动开启分支保护。

命令成功时标准输出是一份 JSON 报告，操作提示写入标准错误，可直接供脚本解析。统计范围包含分组顺序：文件属于第一个匹配组，重排组也需要范围批准。

实际维护案例见 [连续修改记录](examples/continuous-use.md)：从分组重排绕过的复现，到修复后的 JSON 接口改进；记录测试与预算代价，不将单例当作长期效果证明。
