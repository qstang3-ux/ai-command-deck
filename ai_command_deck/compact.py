"""Remove empty output rows for display, leaving stored recordings untouched."""
import re

CSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


class CompactOutput:
    def __init__(self):
        self.content = False
        self.spaces = ''
        self.pending = ''
        self.cr = False
        self.raw = False

    def feed(self, text):
        if self.raw:
            return text
        text = self.pending + text
        self.pending = ''
        output = []
        index = 0
        while index < len(text):
            char = text[index]
            if char == '\x1b':
                match = CSI.match(text, index)
                if match:
                    sequence = match.group()
                    # Cursor-addressed applications depend on exact row positions.
                    if sequence[-1] not in 'mhl' or ('?1049' in sequence or '?1047' in sequence):
                        self.raw = True
                        output.append(('\r' if self.cr else '') + self.spaces + text[index:])
                        self.cr = False
                        self.spaces = ''
                        break
                    output.append(sequence)
                    index = match.end()
                    continue
                if text.startswith('\x1b]', index):
                    ends = [end for end in (text.find('\x07', index+2), text.find('\x1b\\', index+2)) if end >= 0]
                    if ends:
                        end = min(ends)
                        end += 1 if text[end] == '\x07' else 2
                        output.append(text[index:end])
                        index = end
                        continue
                if len(text)-index < 4096 and (index+1 == len(text) or text[index+1] in '[]'):
                    self.pending = text[index:]
                    break
                self.raw = True
                output.append(('\r' if self.cr else '') + self.spaces + text[index:])
                self.cr = False
                self.spaces = ''
                break
            if char == '\r':
                self.cr = True
            elif char == '\n':
                if self.content:
                    output.append('\r\n' if self.cr else '\n')
                self.content = False
                self.spaces = ''
                self.cr = False
            else:
                if self.cr:
                    output.append('\r')
                    self.cr = False
                if not self.content and char in ' \t':
                    self.spaces += char
                    if len(self.spaces) > 4096:
                        self.raw = True
                        output.append(self.spaces + text[index+1:])
                        self.spaces = ''
                        break
                else:
                    output.append(self.spaces + char)
                    self.spaces = ''
                    if ord(char) >= 32:
                        self.content = True
            index += 1
        return ''.join(output)

    def finish(self):
        text = self.pending + ('\r' if self.cr else '')
        self.pending = ''
        self.cr = False
        return text
