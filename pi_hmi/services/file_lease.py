"""Process-owned host file lease; close/crash releases it, no files are deleted."""
import os

class FileLease:
    def __init__(self,path):
        if path.is_symlink():raise ValueError('Lease symlink denied')
        self.stream=path.open('a+b')
        try:
            if self.stream.seek(0,2)==0:self.stream.write(b'0');self.stream.flush()
            self.stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except Exception:self.stream.close();raise
    @property
    def closed(self):return self.stream.closed
    def close(self):self.stream.close()
