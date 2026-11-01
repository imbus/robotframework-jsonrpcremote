from robot.api import ContinuableFailure, FatalError, SkipExecution


class FailingLibrary:
    def fail_normally(self):
        raise ValueError("bad value")

    def skip_the_test(self):
        raise SkipExecution("not today")

    def fail_and_continue(self):
        raise ContinuableFailure("go on")

    def stop_the_run(self):
        raise FatalError("stop all")
