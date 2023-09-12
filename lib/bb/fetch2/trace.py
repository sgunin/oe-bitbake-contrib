class Trace:

    def __init__(self, root, d, ud_dict):
        self.root = root
        for url, ud in ud_dict.items():
            if hasattr(ud, "is_module") and ud.is_module:
               self.is_module = True
               return
        self.is_module = False
        self.d = d
        self.td = {}
        # TODO: do stuff to take a snapshot of the initial state of root dir

    def commit(self, url, ud):
        if self.is_module:
            return
        # TODO: do stuff to take a snapshot of the sources unpacked from url
        # and commit data into self.td

    def write_data(self):
        if self.is_module:
            return
        # TODO: write self.td to some file in <root>/temp
