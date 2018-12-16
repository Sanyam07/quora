import numpy as np
import torch
import os
from sklearn.metrics import f1_score
import warnings
import shutil
import time

from utils import f1_metric, print_duration, get_hash, str_date_time, dict_to_csv


class Learner:

    models_dir = './models'
    best_model_path = './models/best_model.m'
    best_info_path = './models/best_model.info'
    record_dir = './notes'

    def __init__(self, model, dataloaders, loss_func, optimizer, args):
        self.model = model
        self.loss_func = loss_func
        self.optimizer = optimizer
        if len(dataloaders) == 3:
            self.train_dl, self.val_dl, self.test_dl = dataloaders
        elif len(dataloaders) == 2:
            self.train_dl, self.val_dl = dataloaders
        elif len(dataloaders) == 1:
            self.train_dl = dataloaders
            self.val_dl = None
        self.args = args
        if self.args.mode == 'test':
            self.record_path = './notes/test_records.csv'
        elif self.args.mode == 'run':
            self.record_path = './notes/records.csv'

    def fit(self, epoch, eval_every, tresh, early_stop=1, warmup_epoch=2):
        print('Start training!')
        time_start = time.time()
        step = 0
        max_f1 = 0
        no_improve_epoch = 0
        no_improve_in_previous_epoch = False
        fine_tuning = False
        train_record = []
        val_record = []
        losses = []

        torch.backends.cudnn.benchmark = True
        for e in range(epoch):
            if e >= warmup_epoch:
                if no_improve_in_previous_epoch:
                    no_improve_epoch += 1
                    if no_improve_epoch >= early_stop:
                        break
                else:
                    no_improve_epoch = 0
                no_improve_in_previous_epoch = True
            if not fine_tuning and e >= warmup_epoch:
                self.model.embedding.weight.requires_grad = True
                fine_tuning = True
            self.train_dl.init_epoch()
            for train_batch in iter(self.train_dl):
                step += 1
                self.model.train()
                x = train_batch.text.cuda()
                y = train_batch.target.type(torch.Tensor).cuda()
                self.model.zero_grad()
                pred = self.model.forward(x).view(-1)
                loss = self.loss_func(pred, y)
                losses.append(loss.cpu().data.numpy())
                train_record.append(loss.cpu().data.numpy())
                loss.backward()
                self.optimizer.step()
                if step % eval_every == 0:
                    self.model.eval()
                    self.model.zero_grad()
                    val_loss = []
                    tp = 0
                    n_targs = 0
                    n_preds = 0

                    for val_batch in iter(self.val_dl):
                        val_x = val_batch.text.cuda()
                        val_y = val_batch.target.type(torch.Tensor).cuda()
                        val_pred = self.model.forward(val_x).view(-1)
                        val_loss.append(self.loss_func(val_pred, val_y).cpu().data.numpy())
                        val_label = (torch.sigmoid(val_pred).cpu().data.numpy() > tresh).astype(int)
                        val_y = val_y.cpu().data.numpy()
                        tp += sum(val_y + val_label == 2)
                        n_targs += sum(val_y)
                        n_preds += sum(val_label)
                    f1 = f1_metric(tp, n_targs, n_preds)
                    val_record.append({'step': step, 'loss': np.mean(val_loss), 'f1_score': f1})

                    train_loss = np.mean(losses)
                    val_loss = np.mean(val_loss)
                    info = {'best_ep': e, 'step': step, 'train_loss': train_loss,
                            'val_loss': val_loss, 'f1_score': f1}
                    info = self.format_info(info)
                    print('epoch {:02} - step {:06} - train_loss {:.4f} - val_loss {:.4f} - f1 {:.4f}'.format(
                        *list(info.values())))

                    if val_record[-1]['f1_score'] >= max_f1:
                        self.save(info)
                        max_f1 = val_record[-1]['f1_score']
                        no_improve_in_previous_epoch = False
        print_duration(time_start, 'Training time: ')
        m_info = self.load()
        print(f'Best model: {m_info}')

    def predict_probs(self, is_test=False):
        if is_test:
            print('Predicting test dataset...')
            dl = self.test_dl
        else:
            print('Predicting validation dataset...')
            dl = self.val_dl

        self.model.lstm.flatten_parameters()
        self.model.eval()
        y_pred = []
        y_true = []
        ids = []

        dl.init_epoch()
        for batch in iter(dl):
            x = batch.text.cuda()
            if not is_test:
                y_true += batch.target.data.numpy().tolist()
            y_pred += torch.sigmoid(self.model.forward(x).view(-1)).cpu().data.numpy().tolist()
            ids += batch.qid.view(-1).data.numpy().tolist()
        return y_pred, y_true, ids

    def predict_labels(self, is_test=False, tresh=0.5):
        def _choose_tr(self, min_tr, max_tr, tr_step):
            print('Choosing treshold.\n')
            val_pred, val_true, _ = self.predict_probs(is_test=False)
            tmp = [0, 0, 0]  # idx, current_f1, max_f1
            tr = min_tr
            for tmp[0] in np.arange(min_tr, max_tr, tr_step):
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    tmp[1] = f1_score(val_true, np.array(val_pred) > tmp[0])
                if tmp[1] > tmp[2]:
                    tr = tmp[0]
                    tmp[2] = tmp[1]
            print('Best threshold is {:.4f} with F1 score: {:.4f}'.format(tr, tmp[2]))
            return tr, tmp[2]

        y_pred, y_true, ids = self.predict_probs(is_test=is_test)

        if type(tresh) == list:
            tresh, max_f1 = _choose_tr(self, *tresh)
            self.append_info({'best_tr': tresh, 'best_f1': max_f1})

        y_label = (np.array(y_pred) >= tresh).astype(int)
        return y_label, y_true, ids

    def save(self, info):
        os.makedirs(self.models_dir, exist_ok=True)
        torch.save(self.model, self.best_model_path)
        torch.save(info, self.best_info_path)

    @staticmethod
    def format_info(info):
        keys = list(info.keys())
        values = list(info.values())
        for k, v in zip(keys, values):
            info[k] = round(v, 4)
        return info

    @classmethod
    def append_info(cls, dict):
        dict = cls.format_info(dict)
        info = torch.load(cls.best_info_path)
        info.update(dict)
        torch.save(info, cls.best_info_path)

    def record(self):
        os.makedirs(self.record_dir, exist_ok=True)
        subdir = os.path.join(self.models_dir, str_date_time())
        if self.args.mode == 'test':
            subdir +=  '_test'
        os.mkdir(subdir)

        csvlog = os.path.join(subdir, 'info.csv')
        param_dict = {}
        for arg in vars(self.args):
            param_dict[arg] = getattr(self.args, arg)
        info = torch.load(self.best_info_path)
        hash = get_hash()
        param_dict = {'hash':hash, 'subdir':subdir, **param_dict, **info}
        dict_to_csv(param_dict, csvlog, 'w', 'index', reverse=False)
        dict_to_csv(param_dict, self.record_path, 'a', 'columns', reverse=True)
        shutil.copy(self.best_model_path, subdir)


    def load(self):
        self.model = torch.load(self.best_model_path)
        info = torch.load(self.best_info_path)
        return info

