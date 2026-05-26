"""数据库连接池 & 查询工具"""
import pymysql
from dbutils.pooled_db import PooledDB
from flask import g, current_app


pool = None


def init_pool(app):
    """初始化数据库连接池"""
    global pool
    pool = PooledDB(
        creator=pymysql,
        mincached=app.config['DB_POOL_MIN_CACHED'],
        maxcached=app.config['DB_POOL_MAX_CACHED'],
        maxconnections=app.config['DB_POOL_MAX_CONNECTIONS'],
        host=app.config['DB_HOST'],
        port=app.config['DB_PORT'],
        user=app.config['DB_USER'],
        password=app.config['DB_PASSWORD'],
        database=app.config['DB_NAME'],
        charset=app.config['DB_CHARSET'],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def get_conn():
    """获取数据库连接"""
    if 'db_conn' not in g:
        g.db_conn = pool.connection()
    return g.db_conn


def close_conn(exception=None):
    """关闭数据库连接"""
    conn = g.pop('db_conn', None)
    if conn is not None:
        conn.close()


def query(sql, args=None, one=False):
    """执行查询，返回字典列表"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, args)
        if one:
            return cur.fetchone()
        return cur.fetchall()


def execute(sql, args=None):
    """执行写操作，返回受影响行数"""
    conn = get_conn()
    with conn.cursor() as cur:
        rows = cur.execute(sql, args)
        conn.commit()
        return rows


def call_proc(name, args=None):
    """调用存储过程，返回 OUT 参数"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.callproc(name, args)
        conn.commit()
        return cur.fetchall()


def insert(sql, args=None):
    """执行插入操作，返回自增ID"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, args)
        conn.commit()
        return cur.lastrowid


def paginate(sql, args=None, page=1, per_page=None, count_sql=None, count_args=None):
    """分页查询，返回 {items, total, pages, page, per_page}"""
    from flask import current_app
    if per_page is None:
        per_page = current_app.config['PER_PAGE']

    page = max(1, int(page))

    # Count total
    if count_sql:
        total = query(count_sql, count_args or args, one=True)['total']
    else:
        # Auto-wrap: SELECT COUNT(*) FROM (sql) AS _count
        wrapped = f"SELECT COUNT(*) AS total FROM ({sql}) AS _count"
        total = query(wrapped, args, one=True)['total']

    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    offset = (page - 1) * per_page

    items = query(f"{sql} LIMIT {per_page} OFFSET {offset}", args)

    return {
        'items': items,
        'total': total,
        'pages': pages,
        'page': page,
        'per_page': per_page
    }
