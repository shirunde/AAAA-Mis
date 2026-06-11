"""
He Ku Zu (Takuzu / Binairo) 求解器

规则：
  1. 每行、每列中 0（阳/Sun）与 1（阴/Moon）数量各为 n/2
  2. 行、列中不能出现连续三个相同符号
  3. 任意两行、两列不能完全相同
"""


def read_grid():
    """读取输入：首行为 n，随后 n 行 n 个整数（0/1/2）。"""
    n = int(input())
    grid = []
    for _ in range(n):
        row = list(map(int, input().split()))
        grid.append(row)
    return n, grid


def count_in_line(line, val):
    """统计一行/列中某符号已出现的次数。"""
    return sum(1 for x in line if x == val)


def violates_three_in_row(line):
    """
    检查一行/列是否已违反「不能连续三个相同」规则。
    末尾若有连续两个相同且该符号计数已达 n/2，则第三个位置只能填另一种符号（由上层剪枝处理）。
    此处只检测已经出现的三个连续相同。
    """
    for i in range(len(line) - 2):
        if line[i] != 2 and line[i] == line[i + 1] == line[i + 2]:
            return True
    return False


def row_complete_valid(row, n):
    """完整行是否满足计数与三连规则。"""
    if any(x == 2 for x in row):
        return False
    if count_in_line(row, 0) != n // 2 or count_in_line(row, 1) != n // 2:
        return False
    return not violates_three_in_row(row)


def col_complete_valid(grid, col_idx, n):
    """完整列是否满足计数与三连规则。"""
    col = [grid[r][col_idx] for r in range(n)]
    return row_complete_valid(col, n)


def partial_line_valid(line, n):
    """
    部分填写的行/列的剪枝检查：
      - 任一符号数量不超过 n/2
      - 已填部分无三连
      - 若剩余空位恰好只能容纳某一种符号，则另一种符号不能超过配额
    """
    c0 = count_in_line(line, 0)
    c1 = count_in_line(line, 1)
    empty = line.count(2)
    half = n // 2

    if c0 > half or c1 > half:
        return False
    if c0 + empty < half or c1 + empty < half:
        return False
    if violates_three_in_row(line):
        return False

    # 末尾两个相同且第三个位置必须填不同符号时，若该符号配额已满则无解
    if len(line) >= 2 and line[-1] != 2 and line[-1] == line[-2]:
        need = 1 - line[-1]  # 0 或 1
        if (need == 0 and c0 >= half) or (need == 1 and c1 >= half):
            return False

    return True


def rows_unique(grid, n):
    """所有完整行两两不同。"""
    complete = [tuple(row) for row in grid if 2 not in row]
    return len(complete) == len(set(complete))


def cols_unique(grid, n):
    """所有完整列两两不同。"""
    complete_cols = []
    for c in range(n):
        col = [grid[r][c] for r in range(n)]
        if 2 not in col:
            complete_cols.append(tuple(col))
    return len(complete_cols) == len(set(complete_cols))


def row_unique_so_far(grid, row_idx, n):
    """
    当前行若已完整，检查是否与之前完整行重复。
    若当前行未完整，检查其前缀是否与某完整行的前缀一致且该完整行在相同位置已结束——
    实际上只需在整行完成时比较。
    """
    row = grid[row_idx]
    if 2 in row:
        return True
    for r in range(row_idx):
        if 2 not in grid[r] and grid[r] == row:
            return False
    return True


def col_unique_so_far(grid, col_idx, n):
    """当前列填满后是否与左侧完整列重复。"""
    col = [grid[r][col_idx] for r in range(n)]
    if 2 in col:
        return True
    for c in range(col_idx):
        other = [grid[r][c] for r in range(n)]
        if 2 not in other and other == col:
            return False
    return True


def is_valid(grid, n, row, col):
    """在 (row, col) 放置后，检查相关行、列约束及唯一性。"""
    rline = grid[row]
    cline = [grid[r][col] for r in range(n)]

    if not partial_line_valid(rline, n):
        return False
    if not partial_line_valid(cline, n):
        return False

    # 行/列刚填满时做完整校验与唯一性检查
    if 2 not in rline:
        if not row_complete_valid(rline, n):
            return False
        if not row_unique_so_far(grid, row, n):
            return False

    if 2 not in cline:
        if not col_complete_valid(grid, col, n):
            return False
        if not col_unique_so_far(grid, col, n):
            return False

    return True


def find_empty(grid, n):
    """按行优先顺序找下一个待填空格；全部填满返回 (-1, -1)。"""
    for r in range(n):
        for c in range(n):
            if grid[r][c] == 2:
                return r, c
    return -1, -1


def solve(grid, n):
    """
    回溯搜索：对空格依次尝试 0 和 1，每次放置后立即剪枝。
    找到第一个合法解即返回 True。
    """
    row, col = find_empty(grid, n)
    if row == -1:
        # 全盘填满，最终确认行列唯一性
        return rows_unique(grid, n) and cols_unique(grid, n)

    for val in (0, 1):
        grid[row][col] = val
        if is_valid(grid, n, row, col):
            if solve(grid, n):
                return True
        grid[row][col] = 2  # 回溯

    return False


def print_grid(grid, n):
    """按要求输出：每行 n 个数字，无空格。"""
    for r in range(n):
        print("".join(str(grid[r][c]) for c in range(n)))


def main():
    n, grid = read_grid()

    if not solve(grid, n):
        # 题目保证有解；若无解可输出提示（一般评测不需要）
        pass

    print_grid(grid, n)


if __name__ == "__main__":
    main()
