import argparse
import logging
import os
import bb.msg

logger = logging.getLogger('BitBake.BBSetup.common')


class SetupPlugin():
    def __init__(self):
        data = None

    def init(self, d):
        self.data = d

    @staticmethod
    def add_command(subparsers, cmdname, function, *args, **kwargs):
        """Convert docstring for function to help."""
        logger.debug(1, 'Adding command: %s' % cmdname)
        docsplit = function.__doc__.splitlines()
        help = docsplit[0]
        if len(docsplit) > 1:
            desc = '\n'.join(docsplit[1:])
        else:
            desc = help
        subparser = subparsers.add_parser(cmdname, *args, help=help, description=desc, formatter_class=argparse.RawTextHelpFormatter, **kwargs)
        subparser.set_defaults(func=function)
        return subparser

    def get_layer_name(self, layerdir):
        return os.path.basename(layerdir.rstrip(os.sep))
