from robotremoteserver import RobotRemoteServer  # type: ignore[import-untyped]

from JsonRpcRemote.Echo import Echo

RobotRemoteServer(Echo())
