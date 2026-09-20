"""后台任务注册表：名字 → 协程，供 inline 派发与 arq worker 共用。

按名字**调用时**从 flows 模块取当前属性（而非导入时快照函数引用）：
测试用 patch 替换模块属性即可拦截后台任务，与既有测试写法兼容。

新增后台任务：在 flows 里实现协程并在这里登记名字，业务代码用
`dispatch("名字", 参数...)` 启动。
"""

from app.services.scenario import flows

_TASK_ATTRS = {
    "scenario_prepare": "prepare_scenario_challenge",
    "scenario_resolve": "resolve_scenario_action",
    "guess_round": "run_guess_round",
    "guess_verify": "run_guess_verify",
}


def resolve(task_name: str, *args):
    try:
        attr = _TASK_ATTRS[task_name]
    except KeyError:
        raise ValueError(f"未注册的后台任务：{task_name}") from None
    return getattr(flows, attr)(*args)
