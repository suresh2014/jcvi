#!/usr/bin/env python
# -*- coding: UTF-8 -*-

"""
Run bowtie2 command and skips the manual run of naming intermediate output
files. Bowtie2 help:

<http://bowtie-bio.sourceforge.net/bowtie2/index.shtml>
"""

import sys
import logging
import os.path as op

from jcvi.apps.base import OptionParser

from jcvi.formats.base import BaseFile
from jcvi.utils.cbook import percentage
from jcvi.formats.sam import output_bam, get_prefix
from jcvi.apps.base import ActionDispatcher, need_update, \
                sh, debug
debug()


first_tag = lambda fp: fp.next().split()[0]


class BowtieLogFile (BaseFile):
    """
    Simple file that contains mapping rate:

    100000 reads; of these:
      100000 (100.00%) were unpaired; of these:
        88453 (88.45%) aligned 0 times
        9772 (9.77%) aligned exactly 1 time
        1775 (1.77%) aligned >1 times
    11.55% overall alignment rate
    """
    def __init__(self, filename):

        super(BowtieLogFile, self).__init__(filename)
        fp = open(filename)
        self.total = int(first_tag(fp))
        self.unpaired = int(first_tag(fp))
        self.unmapped = int(first_tag(fp))
        self.unique = int(first_tag(fp))
        self.multiple = int(first_tag(fp))
        self.mapped = self.unique + self.multiple
        self.rate = float(first_tag(fp).rstrip("%"))
        fp.close()

    def __str__(self):
        return "Total mapped: {0}".format(\
                percentage(self.mapped, self.total))

    __repr__ = __str__


def main():

    actions = (
        ('index', 'wraps bowtie2-build'),
        ('align', 'wraps bowtie2'),
            )
    p = ActionDispatcher(actions)
    p.dispatch(globals())


def check_index(dbfile, grid=False):
    safile = dbfile + ".1.bt2"
    if need_update(dbfile, safile):
        cmd = "bowtie2-build {0} {0}".format(dbfile)
        sh(cmd, grid=grid)
    else:
        logging.error("`{0}` exists. `bowtie2-build` already run.".format(safile))

    return safile


def index(args):
    """
    %prog index database.fasta

    Wrapper for `bowtie2-build`. Same interface, only adds grid submission.
    """
    p = OptionParser(index.__doc__)
    p.set_params()
    p.set_grid()

    opts, args = p.parse_args(args)

    if len(args) != 1:
        sys.exit(not p.print_help())

    extra = opts.extra
    grid = opts.grid

    dbfile, = args
    safile = check_index(dbfile, grid=grid)


def align(args):
    """
    %prog align database.fasta read1.fq [read2.fq]

    Wrapper for `bowtie2` single-end or paired-end, depending on the number of args.
    """
    from jcvi.formats.fastq import guessoffset

    p = OptionParser(align.__doc__)
    p.add_option("--firstN", default=0, type="int",
                 help="Use only the first N reads [default: all]")
    p.add_option("--unmapped", default=None,
                 help="Write unmapped reads to file [default: %default]")
    p.add_option("--log", default=False, action="store_true",
                 help="Write log file [default: %default]")
    p.set_sam_options()

    opts, args = p.parse_args(args)
    extra = opts.extra
    grid = opts.grid

    PE = True
    if len(args) == 2:
        logging.debug("Single-end alignment")
        PE = False
    elif len(args) == 3:
        logging.debug("Paired-end alignment")
    else:
        sys.exit(not p.print_help())

    extra = opts.extra
    grid = opts.grid
    firstN = opts.firstN
    unmapped = opts.unmapped

    dbfile, readfile = args[0:2]
    safile = check_index(dbfile, grid=grid)
    prefix = get_prefix(readfile, dbfile)

    samfile = (prefix + ".bam") if opts.bam else (prefix + ".sam")
    logfile = prefix + ".log" if opts.log else None
    offset = guessoffset([readfile])

    if not need_update(safile, samfile):
        logging.error("`{0}` exists. `bowtie2` already run.".format(samfile))
        return samfile, logfile

    cmd = "bowtie2 -x {0}".format(dbfile)
    if PE:
        r1, r2 = args[1:3]
        cmd += " -1 {0} -2 {1}".format(r1, r2)
        if unmapped:
            cmd += " --un-conc {0}".format(unmapped)
    else:
        cmd += " -U {0}".format(readfile)
        if unmapped:
            cmd += " --un {0}".format(unmapped)

    if firstN:
        cmd += " --upto {0}".format(firstN)
    cmd += " -p {0}".format(opts.cpus)
    cmd += " --phred{0}".format(offset)
    cmd += " {0}".format(extra)

    cmd = output_bam(cmd, bam=opts.bam)
    sh(cmd, grid=grid, outfile=samfile, errfile=logfile, threaded=opts.cpus)
    return samfile, logfile


if __name__ == '__main__':
    main()