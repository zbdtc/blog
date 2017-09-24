import asyncio
import orm
import Models
import logging; logging.basicConfig(level=logging.INFO)

async def test(loop):
    await orm.create_pool(loop, host='127.0.0.1', port=3306, user='root', password='12283',db='awesome')
    u = Models.User
    print(u)
    a = await u.findAll()
    print(a)
    print('nnnnnnnnnn')

loop = asyncio.get_event_loop()
loop.run_until_complete(test(loop))
# orm.__pool.close()
# loop.run_until_complete(orm.__pool.wait_closed())
loop.run_forever()