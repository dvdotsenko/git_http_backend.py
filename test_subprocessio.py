import random
import unittest
import subprocessio
import tempfile

class MainTestCase(unittest.TestCase):

    def getiter(self, cmd, input):
        try:
            return subprocessio.SubprocessIOChunker(
                cmd,
                input,
                buffer_size = 65536,
                chunk_size = 4096
                )
        except (EnvironmentError) as e:
            # just because.
            print str(e)
            raise e

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_01_string_throughput(self):
        cmd = 'cat'
        input = 'This is a test string'
        _r = self.getiter(
            cmd,
            input
            )
        self.assertEqual(
            "".join(_r),
            input
            )

    def test_02_io_throughput(self):
        cmd = 'cat'
        size = 128000
        i = size
        input = tempfile.TemporaryFile()
        checksum = 0
        while i:
            _r = random.randrange(32,255)
            checksum += _r
            input.write(chr(_r))
            i -= 1
        input.seek(0)

        _r = self.getiter(
            cmd,
            input
            )

        for e in _r:
            size -= len(e)
            for l in e:
                checksum -= ord(l)

        self.assertEqual(
            size,
            0
            )

        self.assertEqual(
            checksum,
            0
            )


if __name__ == "__main__":
    unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite([
            unittest.TestLoader().loadTestsFromTestCase(MainTestCase),
        ])
    )