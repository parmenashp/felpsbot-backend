import prisma as prisma_module
from prisma import Prisma

prisma = Prisma()

prisma_module.register(prisma)
