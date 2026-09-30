"""Подделки для тестов: лист Google Таблицы в памяти."""


class FakeSheet:
    def __init__(self):
        self.tabs: dict[str, list[list[str]]] = {}
        self.writes = 0

    def read(self, tab):
        return [list(row) for row in self.tabs.setdefault(tab, [])]

    def update_rows(self, tab, rows):
        grid = self.tabs.setdefault(tab, [])
        for number, values in rows.items():
            while len(grid) < number:
                grid.append([])
            grid[number - 1] = list(values)
        self.writes += 1

    def append_rows(self, tab, rows):
        self.tabs.setdefault(tab, []).extend(list(row) for row in rows)
        self.writes += 1

    def delete_rows(self, tab, numbers):
        for number in sorted(numbers, reverse=True):
            del self.tabs[tab][number - 1]
        self.writes += 1

    def rows(self, tab) -> list[dict[str, str]]:
        header, *body = self.tabs[tab]
        return [dict(zip(header, row, strict=False)) for row in body]

    def row(self, tab, **where) -> dict[str, str]:
        found = [r for r in self.rows(tab) if all(r[k] == v for k, v in where.items())]
        assert len(found) == 1, found
        return found[0]

    def edit(self, tab, where: dict, **changes):
        header = self.tabs[tab][0]
        for cells in self.tabs[tab][1:]:
            row = dict(zip(header, cells, strict=False))
            if all(row[k] == v for k, v in where.items()):
                for name, value in changes.items():
                    cells[header.index(name)] = value
                return
        raise AssertionError(f"no row {where}")
