#!/usr/bin/env python
# -*- coding: utf-8 -*-
from optparse import OptionParser, OptionGroup, OptionValueError
from shutil import copyfile
from string import uppercase
from xml.dom import minidom
import codecs
import logging
import os.path
import re
import sys

STDIN = STDOUT = '-'
ENCODING = 'utf-8'
EMPTY_TRANS = '_'
COLL_NAME_SEP = ' - '

VERSION = '1.0'

TRANSLATE_CHARS = {
    u'А': 'A',
    u'Б': 'B',
    u'В': 'V',
    u'Г': 'G',
    u'Д': 'D',
    u'Е': 'E',
    u'Ё': 'E',
    u'Ж': 'Z',
    u'З': 'Z',
    u'И': 'I',
    u'Й': 'I',
    u'К': 'K',
    u'Л': 'L',
    u'М': 'M',
    u'Н': 'N',
    u'О': 'O',
    u'П': 'P',
    u'Р': 'R',
    u'С': 'S',
    u'Т': 'T',
    u'У': 'U',
    u'Ф': 'F',
    u'Х': 'H',
    u'Ц': 'C',
    u'Ч': 'C',
    u'Ш': 'W',
    u'Щ': 'W',
    u'Ы': 'Y',
    u'Э': 'E',
    u'Ю': 'U',
    u'Я': 'A'
}

def split_path(path):
    head, tail = os.path.split(path)
    if head:
        return split_path(head) + [tail, ]
    else:
        return [tail, ]

class StripDir:
    def __init__(self, strip_dir):
        self.strip_dir = strip_dir

    def strip(self, path):
        return os.path.relpath(path, self.strip_dir)

class StripWord:
    def __init__(self, word, first = False, last = False):
        self.first = first
        self.last = last
        assert word is not None, 'Argument word is required.'
        self.word = word

    def strip(self, path):
        p = split_path(path)
        if self.word in map(lambda p: p.lower(), p):
            if self.first:
                i = p.index(self.word) + 1
            elif self.last:
                i = len(p) - list(reversed(p)).index(self.word)
            else:
                i = 0
            return reduce(lambda a, b: os.path.join(a, b), p[i:])
        return path

class Prs505collection:
    def __init__(self, in_file, strip = None):
        self.dom = minidom.parse(in_file)
        self.norm_pattern = re.compile('\s+')
        self.strip = strip

    def translate(self, char):
        if TRANSLATE_CHARS.has_key(char.upper()):
            return TRANSLATE_CHARS[char.upper()]
        else:
            return EMPTY_TRANS

    def norm(self, value):
        return self.norm_pattern.sub(' ', value.strip())

    def index_attribute(self, node, attr_name):
        if not node.attributes.has_key(attr_name):
            return
        value = self.norm(node.attributes[attr_name].value)
        if len(value) > 3 and value[0] in uppercase + EMPTY_TRANS and value[1] == ':' and value[2] == ' ':
            return
        value = self.translate(value[0]) + ': ' + value
        node.setAttribute(attr_name, value)

    def proc_text(self, text):
        self.index_attribute(text, 'author')
        self.index_attribute(text, 'title')

    def get_attr(self, node, attr_name, default = None):
        if node.attributes.has_key(attr_name):
            return node.attributes[attr_name].value
        else:
            return default

    def get_coll_name(self, node):
        path = self.get_attr(node, 'path')
        if path:
            if self.strip:
                path = self.strip.strip(path)
            return COLL_NAME_SEP.join(split_path(path)[:-1])

    def make_collecation(self, max_id, colls):
        id = max_id + 1
        cache = self.dom.getElementsByTagName('cache')[0]
        for pl in cache.getElementsByTagName('playlist'):
            logging.debug('Remove existing collection: %s', self.get_attr(pl, 'title'))
            cache.removeChild(pl)
        logging.info('Creating collection sets')
        for col in colls:
            pl = self.create_collection(id, col, colls[col])
            cache.appendChild(pl)
            id += 1

    def create_collection(self, id, title, items):
        logging.debug('Create collection: %s' % title)
        pl = self.dom.createElement('playlist')
        pl.setAttribute('id', str(id))
        pl.setAttribute('sourceid', '0')
        pl.setAttribute('title', title)
        for item_id in items:
            item = self.dom.createElement('item')
            item.setAttribute('id', str(item_id))
            pl.appendChild(item)
        return pl

    def make_indexes(self):
        texts = self.dom.getElementsByTagName('text')
        max_id = 0
        colls = dict()
        logging.info('Index titles and authors')
        for text in texts:
            self.proc_text(text)
            id = int(self.get_attr(text, 'id', 0))
            max_id = max(max_id, id)

            col = self.get_coll_name(text)
            if colls.has_key(col):
                colls[col].append(id)
            else:
                colls[col] = [id,]
        return max_id, colls

    def do(self):
        max_id, colls = self.make_indexes()
        self.make_collecation(max_id, colls)

    def write(self, out_file):
        self.do()
        self.dom.writexml(out_file, encoding = ENCODING)

def setup_optparser():
    parser = OptionParser(
        version = "%prog " + VERSION,
        description = 'Script to process Sony PRS-505 catalog file.'
    )
    parser.add_option('-i', '--input', dest = 'input_file_name', default = STDIN,
                      help = 'read xml from FILE (if - then read from stdin)', metavar = 'FILE')
    parser.add_option('-o', '--output', dest = 'output_file_name', default = STDOUT,
                      help = 'write xml to FILE (if - then write to stdout)', metavar = 'FILE')
    parser.add_option('-q', '--quiet', action = 'store_const', const = logging.ERROR,
                      dest = 'log_level', help = 'be quiet')
    parser.add_option('-v', '--verbose', action = 'store_const', const = logging.DEBUG,
                      dest = 'log_level', help = 'make more noise')

    strip_group = OptionGroup(parser, 'Strip Options', 'Only one strip option allowed.')

    def strip_dir_callback(option, opt_str, value, parser):
        if parser.values.strip:
            raise OptionValueError('only one strip option accepted')
        setattr(parser.values, option.dest, StripDir(value))

    def strip_last_callback(option, opt_str, value, parser):
        if parser.values.strip:
            raise OptionValueError('only one strip option accepted')
        setattr(parser.values, option.dest, StripWord(value, last = True))

    def strip_first_callback(option, opt_str, value, parser):
        if parser.values.strip:
            raise OptionValueError('only one strip option accepted')
        setattr(parser.values, option.dest, StripWord(value, first = True))

    strip_group.add_option('--strip-dir', dest = 'strip', type = 'string',
                           action = 'callback', callback = strip_dir_callback,
                           help = 'strip DIR from path', metavar = 'DIR')
    strip_group.add_option('--strip-last', dest = 'strip', type = 'string',
                           action = 'callback', callback = strip_last_callback,
                           help = 'strip path to last WORD', metavar = 'WORD')
    strip_group.add_option('--strip-first', dest = 'strip', type = 'string',
                           action = 'callback', callback = strip_first_callback,
                           help = 'strip path to first WORD', metavar = 'WORD')
    parser.add_option_group(strip_group)
    return parser

def main():
    parser = setup_optparser()
    (options, args) = parser.parse_args()

    logging.basicConfig(level = options.log_level or logging.INFO,
                        format = '%(levelname)8s: %(message)s')

    if options.input_file_name == STDIN:
        in_file = sys.stdin
        logging.debug('Read data from stdin')
    else:
        if os.path.isfile(options.input_file_name):
            in_file = open(options.input_file_name, 'r')
            logging.debug('Read data from file: %s' % options.input_file_name)
        else:
            logging.error('No file: %s' % options.input_file_name)
            sys.exit(1)
    if options.output_file_name == STDOUT:
        out_file = codecs.getwriter(ENCODING)(sys.stdout)
        logging.debug('Write result to stdout')
    else:
        if os.path.isfile(options.output_file_name):
            bak_file = options.output_file_name + '.bak'
            logging.info('Create backup of output file: %s -> %s' % (
                options.output_file_name, bak_file
            ))
            copyfile(options.output_file_name, bak_file)
            logging.warning('Result files exists and will be overwrited')
        out_file = codecs.open(options.output_file_name, 'w', ENCODING)
        logging.debug('Write result to file: %s' % options.output_file_name)

    try:
        c = Prs505collection(in_file, strip = options.strip)
        c.write(out_file)
    finally:
        in_file.close()
        out_file.close()

if __name__ == '__main__':
    main()
