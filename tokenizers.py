import re
import spacy


def lower_spacy(x):
    x = x.lower()
    spacy_en = spacy.load('en')
    return [tok.text for tok in spacy_en.tokenizer(x)]

class LowerSpacy(object):
    def __init__(self):
        pass

    def __call__(self, text):
        spacy_en = spacy.load('en')
        return lambda x: [tok.text for tok in spacy_en.tokenizer(x)]



class WhitespaceTokenizer(object):
    def __init__(self):
        pass

    def __call__(self, text):
        words = text.split(' ')
        return words


class CustomTokenizer(object):
    def __init__(self):
        #self.allowed_re = re.compile('^[A-Za-z0-9.,?!()]*$')
        self.punct = re.compile('[,!.?()]')

    def __call__(self, text):
        substrings = text.split(' ')
        tokens = []
        for ss in substrings:
            punct_match = self.punct.search(ss)
            if punct_match:
                start = punct_match.start()
                ss_tokens = [ss[:start], ss[start], ss[start + 1:]]
                ss_tokens = [t for t in ss_tokens if len(t) > 0]
            else:
                ss_tokens = [ss]
            tokens.extend(ss_tokens)
        return tokens