import aiomysql
import asyncio
import logging

import time

def log(sql, args=()):
	logging.info('SQL: %s' % sql)

async def create_pool(loop, **kw):
	logging.info('create database connection pool...')
	global __pool
	__pool = await aiomysql.create_pool(
		host=kw.get('host', 'localhost'),
		port=kw.get('port', 3306),
		user=kw.get('user', 'user'),
		password=kw['password'],
		db=kw['database'],
		charset=kw.get('chatset','utf8'),
		autocommit=kw.get('autocommit', True),
		maxsize=kw.get('maxsize', 10),
		minsize=kw.get('minsize',1),
		loop=loop
	)


async def select(sql, args, size=None):
	print('xxxxxx')
	log(sql, args)
	global __pool
	with (await __pool) as conn:
		cur = await conn.cursor(aiomysql.DictCursor) #创建一个结果为字典的游标
		print('ok1')
		await cur.execute(sql.replace('?', '%s'), args or ())#执行sql语句，将sql语句中的‘？’替换成‘%s'
		print('ok2')
		#如果指定了数量，就返回指定数量的记录，如果没有，就返回所有记录
		if size:
			rs = await cur.fetchmany(size)
		else:
			rs = await cur.fetchall()
		print('ok')
		await cur.close()
		logging.info('row returned:%s' % len(rs))
		return rs

async def execute(sql, args, autocommit=True):
	log(sql)
	with (await __pool) as conn:
		if not autocommit:
			await conn.begin()
		try:
			async with conn.cursor(aiomysql.DictCursor) as cur:
				await cur.execute(sql.replace('?', '%s'), args)
				affected = cur.rowcount
			if not autocommit:
				await conn.commit()
		except BaseException as e:
			if not autocommit:
				await conn.rollback()
			raise
		return affected

def create_args_string(num):
	L = []
	for n in range(num):
		L.append('?')
	return ', '.join(L)

#########orm把一张表作为一个类，每行都是一个实例，每个字段都是实例的一个属性##########
class Field(object):
	def __init__(self, name, column_type, primary_key, default):
		self.name = name #列名称
		self.column_type = column_type #数据类型
		self.primary_key = primary_key#是否是主键
		self.default = default#默认值

	def __str__(self): 
		return'<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)

class StringField(Field): #str类型字段对象
	def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
		super(StringField,self).__init__(name, ddl, primary_key, default)

class BooleanField(Field): #布尔值类型对象
	def __init__(self, name=None, default=False):
		super().__init__(name, 'boolean', False, default)

class IntegerField(Field): #整型类型字段对象
	def __init__(self, name=None, primary_key=False, default=0):
		super().__init__(name, 'bigint', primary_key, default)

class FloatField(Field): #浮点类型字段对象
	def __init__(self, name=None, primary_key=False, default=0.0):
		super().__init__(name, 'real', primary_key, default)

class TextField(Field): #文本类型字段对象
	def __init__(self, name=None, default=None):
		super().__init__(name, 'text', False, default)

#########定义Model的metaclass####
class ModelMetaclass(type):
	def __new__(cls, name, bases, attrs):
		if name == 'Model': #如果是创建Model类的实例，正常创建
			return type.__new__(cls, name, bases, attrs)

		tableName = attrs.get('__table__',None) or name # 获取类（表）的名字
		logging.info('found model:%s(table(%s)' % (name, tableName)) #打印类名和表名（应该是一致的rua）
		mappings=dict()
		fields = []
		primaryKey = None
		for k, v in attrs.items():
			if isinstance(v, Field):
				logging.info('  found mapping: %s ==> %s' % (k, v))#打印键名和值（
				mappings[k]=v
				if v.primary_key:
					if primaryKey: # 如果‘primarykey’这个变量存在值，提示错误错：重复主键
						raise BaseException('Duplicate primary key for fields:%s' % k)
					primaryKey = k
				else:
					fields.append(k)
		if not primaryKey: #在执行上面的for循环后，如‘primarykey’这个变量的值还是None，提示：主键未找到
			raise BaseException('Primary key not found')
		for k in mappings.keys():
			attrs.pop(k) #删除类属性，防止和实例属性冲突
		escaped_fields = list(map(lambda f: '`%s`' % f, fields)) #
		attrs['__mappings__'] = mappings #保存属性和列的映射关系
		attrs['__table__'] = tableName
		attrs['__primarykey__'] = primaryKey#保存主键名
		attrs['__fields__'] = fields #保存除主键以外的属性名
		###构造默认的select，insert，updat，delete语句模板####
		attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ','.join(escaped_fields), tableName)
		attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
		attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
		attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
		return type.__new__(cls, name, bases, attrs)

class Model(dict, metaclass=ModelMetaclass):
	def __init__(self, **kw):
		super(Model, self).__init__(**kw)

	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Model' object has no attribute '%s'" % key)

	def __setattr__(self, key, value):
		self[key] = value

	def getValue(self, key):
		return getattr(self, key, None)

	def getValueOrDefault(self, key): #使用save方法时调用
		value = getattr(self, key, None)
		if value is None:
			field = self.__mappings__[key] #创建实例时，假设参数key使用的是默认值，那么key参数的值并没有被输入，此时self['key']不存在，上面getattr返回None
			print(key, field)
			if field.default is not None:
				print('aa')
				value = field.default() if callable(field.default) else field.default
				logging.debug('using default value for %s: %s' % (key, str(value)))
				setattr(self, key, value)
		return value

	@classmethod
	async def findAll(cls, where=None, args=None, **kw):
		###find objects by where clause####
		sql = [cls.__select__]
		if where:
			sql.append('where')
			sql.append(where)
		if args is None:
			args=[]
		orderBy = kw.get('orderBy', None)
		if orderBy:
			sql.append('order By')
			sql.append(orderBy)
		limit = kw.get('limit', None)
		if limit is not None:
			sql.append('limit')
			if isinstance(limit, int):
				sql.append('?')
				args.append(limit)
			elif isinstance(limit, tuple) and len(limit) == 2:
				sql.append('?, ?')
				args.extend(limit)
			else:
				raise ValueError('Invalid limit value: %s' % str(limit))
		print('start await rs')
		rs = await select(' '.join(sql), args)
		print('rs===============',rs)
		print([r for r in rs])
		return [cls(**r) for r in rs]
	
	#统计用
	@classmethod
	async def findNumber(cls, selectField, where=None, args=None):
		####find number by select and where#####
		sql = ['select %s _num_ from `%s`' % (selectField, cls.__table__)]
		if where:
			sql.append('where')
			sql.append(where)
		print(sql)
		rs = await select(''.join(sql), args, 1)
		if len(rs) == 0:
			return None
		return rs[0]['_num_']

	@classmethod
	async def find(cls, pk): 
		###find object by primary key###
		rs = await select(('%s where `%s` = ?' % (cls.__select__, cls.__primarykey__)), [pk], 1)
		if len(rs) == 0:
			return None
		return cls(**rs[0])

	async def save(self):
		args = list(map(self.getValueOrDefault,self.__fields__))
		args.append(self.getValueOrDefault(self.__primarykey__))
		rows = await execute(self.__insert__, args)
		if rows != 1:
			logging.warn('failed to insert record: affected rows: %s' % rows)

	async def update(self):
		args = list(map(self.getValueOrDefault,self.__fields__))
		args.append(self.getValueOrDefault(self.__primarykey__))
		rows = await execute(self.__update__, args)
		if rows != 1:
			logging.warn('failed to update by primary key: affected rows: %s' % rows)

	async def remove(self):
		args = [self.getValueOrDefault(self.__primarykey__)]
		rows = await execute(self.__delete__, args)
		if rows != 1:
			logging.warn('failed to remove by primary key: affected rows: %s' % rows)

