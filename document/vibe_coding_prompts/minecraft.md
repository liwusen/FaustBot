## 请阅读并理解前后端代码，完成以下任务：

# 设计一套为这个项目准备的Minecraft操作系统

### 功能简述

[重要]1.简述：通过minefayer使得 FaustBot 主 Agent 拥有操作Minecraft游戏的能力，使得用户可以通过和 FaustBot 玩游戏

### 技术实现&&功能要求

[重要]1.请使用Minefayer进行与Minecraft的通信，与对Minecraft的操作。

2.你需要实现一个Node.js程序，称为mc-operator，由它调用Minefayer，并且连接至Minecraft服务器进行操作

        让它开放API，来允许主Agent操作Minecraft

        可以使用 

3.mc-operator 应该开放一个 Websockets 作为主API，与主程序双向通信

4.在FaustBot主程序中添加用于操作Minecraft的工具，以及当minecraft发生事件时允许唤醒模型的Trigger。

    4.1 工具应当包括一个 Minecraft Command Tool 接受一个 Minecraft 命令 使用Json 格式化 比如一个示例是

> ```json
> {
>     "name":"look-at-a-player",
>     "args":{
>         "player-name":"TestPlayer"
>     }
> 
> }
> ```

    并且这个工具应该支持返回值，示例



> ```json
> {
>     "name":"get-mobs-around",
>     "args":{
>         "radius":5
>     }
> }
> ```
> 
> 返回：
> 
> ```json
> {"mobs":[
>     {
>     "type":"zombie",
>     "pos-x-y-z":[114,114,114],
>     "id":"<MINECRAFT 实体ID>"
>     }
> ]}
> ```

    4.2 需要支持的操作包括但不限于 eat-food,look-at-player，go-to-position等基础minecraft操作，同时也要参考Mindcraft，实现它支持的所有操作

    4.3 Trigger 应该是由 通过Minefayer 获取到的 Minecraft 事件触发的
            应当至少包括以下类型事件，并且触发后通知Agent时应该包含相关信息（如周边信息等）

            应该实现一个通用 mc-event-tigger

> | 事件类型           | 解释            |
> | -------------- | ------------- |
> | join-mc-server | 成功加入mc服务器后的回调 |
> | hurted         | 游戏中受伤         |
> | mc-message     | 收到游戏消息        |

5.前后端应该使用 命令模式(FaustBot 发令=>mc-operater) 执行 & 观察者模式（后端产生事件=>通知FaustBot）的设计模式

6.应该由FaustBot Agent自己决定通过调用工具加入服务器

7.应该让FaustBot Agent直接操作游戏

8.添加一个 agent_lock,对调用Agent的操作上锁

9.可以参考 Mindcraft ,同时请仔细阅读 minefayer 的文档

> 在这个目录中存放了 mindcraft 与 minefayer的Git仓库，供你阅读
> 
> ```
> faust\backend\minecraft\__dev__
> ```

10. mc-operater 放在 faust/backend/minecraft下
    python 放在 faust/backend/backend-main.py && faust/backend/faust_backend

### 实现过程

0.在附件中给你的是我认为和这个功能强相关的代码

1.仔细思考我的需求，考虑这个功能真正对用户的意义与作用

2.阅读前后端代码,以及两个项目的源码&&文档

2.5 给出编写方案以及解释，等待我审批检查

3.进行修改

    做到新修改的代码尽可能符合这个项目原始的设计思路


