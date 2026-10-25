from tests.fixtures.reliance_quarterly import INFO, QUARTERLY


class FakeClient:
    def __init__(self, stmt=QUARTERLY, info=INFO, fail_first=0):
        self.stmt, self._info, self.fail_first, self.calls = stmt, info, fail_first, 0

    def quarterly_income_stmt(self):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise ConnectionError("boom")
        return self.stmt

    def info(self):
        return self._info
