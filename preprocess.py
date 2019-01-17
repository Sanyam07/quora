import torch
import time
import random
import pickle
import os
from functools import partial
import torchtext.data as data

from utils import print_duration
from my_torchtext import MyTabularDataset, MyVectors
from choose import choose_tokenizer


def normal_init(tensor, std):
    return torch.randn_like(tensor) * std


class Data:
    def __init__(self, train_csv, test_csv, cache):
        self.test_csv = test_csv
        self.train_csv = train_csv
        self.cache = cache
        self.text = None
        self.qid = None
        self.train = None
        self.test = None
        self.target = None

    def preprocess(self, tokenizer_name, var_length=False):
        # types of csv columns
        time_start = time.time()
        tokenizer = choose_tokenizer(tokenizer_name)
        self.text = data.Field(batch_first=True, tokenize=tokenizer, include_lengths=var_length)
        self.qid = data.Field()
        self.target = data.Field(sequential=False, use_vocab=False, is_target=True)

        # read and tokenize data
        print('read and tokenize data...')
        self.train = MyTabularDataset(path=self.train_csv, format='csv',
                                 fields={'qid': ('qid', self.qid),
                                         'question_text': ('text', self.text),
                                         'target': ('target', self.target)})

        self.test = MyTabularDataset(path=self.test_csv, format='csv',
                                fields={'qid': ('qid', self.qid),
                                        'question_text': ('text', self.text)})
        self.text.build_vocab(self.train, self.test, min_freq=1)
        self.qid.build_vocab(self.train, self.test)
        print_duration(time_start, 'time to read and tokenize data: ')


    def embedding_lookup(self, embedding, unk_std, max_vectors, to_cache):
        print('embedding lookup...')
        time_start = time.time()
        unk_init = partial(normal_init, std=unk_std)
        self.text.vocab.load_vectors(MyVectors(embedding, cache=self.cache, to_cache=to_cache, unk_init=unk_init, max_vectors=max_vectors))
        print_duration(time_start, 'time for embedding lookup: ')
        return

    def split(self, kfold, split_ratio, stratified, is_test, seed):
        random.seed(seed)
        if kfold:
            data_iter = self.train.split_kfold(kfold, is_test=is_test, stratified=stratified, strata_field='target', random_state=random.getstate())
        else:
            data_iter = self.train.split(split_ratio, stratified=stratified, strata_field='target', random_state=random.getstate())
        return data_iter


def iterate(train, val, test, batch_size):
    train_iter = data.BucketIterator(dataset=train,
                                     batch_size=batch_size,
                                     sort_key=lambda x: x.text.__len__(),
                                     shuffle=True,
                                     sort=False,
                                     sort_within_batch=True)

    val_iter = data.BucketIterator(dataset=val,
                                   batch_size=batch_size,
                                   sort_key=lambda x: x.text.__len__(),
                                   train=False,
                                   sort=False,
                                   sort_within_batch=True)

    test_iter = data.BucketIterator(dataset=test,
                                    batch_size=batch_size,
                                    sort_key=lambda x: x.text.__len__(),
                                    sort=False,
                                    train=False,
                                    sort_within_batch=True)
    return train_iter, val_iter, test_iter
