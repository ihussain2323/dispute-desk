import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from intake import Conflict, advance, case, connection, initialize, start


class IntakeTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db=Path(tmp.name)/'case.sqlite'
        initialize(self.db)
        self.call=start(self.db)

    def turn(self,text):
        self.call=advance(self.db,self.call['call_id'],self.call['seq'],str(self.call['seq']),text)
        return self.call['stage']

    def test_correction_and_explicit_confirmation(self):
        self.assertEqual(self.turn('Harbor Books or Maple Market'), 'payment')
        self.assertEqual(self.turn('Harbor Books'),'reason')
        self.assertEqual(self.turn('never arrived'),'confirm')
        self.assertEqual(self.turn('I do not confirm'),'confirm')
        self.assertEqual(self.turn('start over'),'payment')
        self.turn('North Star Coffee')
        self.turn('duplicate charge')
        with connection(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM cases').fetchone()[0],0)
        self.turn('confirm')
        self.assertEqual(case(self.db,self.call['case_id'])['transaction']['id'],'T103')

    def test_cancel(self):
        self.turn('Maple Market')
        self.turn('not a duplicate charge')
        self.assertEqual(self.call['stage'],'reason')
        self.assertEqual(self.turn('cancel'),'cancelled')
        with self.assertRaises(Conflict):
            self.turn('confirm')

    def test_concurrent_confirmation(self):
        self.turn('maple market')
        self.turn('charged twice')
        with ThreadPoolExecutor(2) as pool:
            calls=list(pool.map(lambda _: advance(self.db,self.call['call_id'],2,'req','confirm'),range(2)))
        self.assertEqual(calls[0],calls[1])
        with connection(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM cases').fetchone()[0],1)
        with self.assertRaises(Conflict):
            advance(self.db,self.call['call_id'],2,'another','confirm')
