import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import BankCardDeposit
from app.services.bank_funds import allocate_fifo


class BankFundsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            BankCardDeposit(usdt_amount=10.01, c2c_rate=6.5, cny_cost=65.07, chain_fee=.01, actual_received=10, remaining_usdt=10),
            BankCardDeposit(usdt_amount=10.01, c2c_rate=7, cny_cost=70.07, chain_fee=.01, actual_received=10, remaining_usdt=10),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_fifo_preview_crosses_lots_without_mutating(self):
        allocations, shortfall = allocate_fifo(self.db, 11)
        self.assertEqual([item.usdt_amount for item in allocations], [10, 1])
        self.assertEqual(shortfall, 0)
        self.assertEqual(round(sum(item.usdt_amount * item.deposit.c2c_rate for item in allocations), 2), 72)
        self.assertEqual(self.db.get(BankCardDeposit, 1).remaining_usdt, 10)

    def test_fifo_consume_and_partial_coverage(self):
        allocations, shortfall = allocate_fifo(self.db, 25, consume=True)
        self.assertEqual(len(allocations), 2)
        self.assertEqual(shortfall, 5)
        self.assertEqual(self.db.get(BankCardDeposit, 1).remaining_usdt, 0)
        self.assertEqual(self.db.get(BankCardDeposit, 2).remaining_usdt, 0)


if __name__ == "__main__":
    unittest.main()
