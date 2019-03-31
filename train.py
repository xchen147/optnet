#!/usr/bin/env python3

import argparse
import csv
import os
import shutil
from tqdm import tqdm

try: import setGPU
except ImportError: pass

import torch    
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable

import numpy as np
import numpy.random as npr

import sys

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
plt.style.use('bmh')

import setproctitle

import models

import sys
from IPython.core import ultratb
sys.excepthook = ultratb.FormattedTB(mode='Verbose',
     color_scheme='Linux', call_pdb=1)

def print_header(msg):
    print('===>', msg)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-cuda', action='store_true')
    parser.add_argument('--boardSz', type=int, default=2)
    parser.add_argument('--batchSz', type=int, default=150)
    parser.add_argument('--testBatchSz', type=int, default=200)
    parser.add_argument('--nEpoch', type=int, default=100)
    parser.add_argument('--testPct', type=float, default=0.1)
    parser.add_argument('--save', type=str)
    parser.add_argument('--work', type=str, default='work')
    subparsers = parser.add_subparsers(dest='model')
    subparsers.required = True
    fcP = subparsers.add_parser('fc')
    fcP.add_argument('--nHidden', type=int, nargs='+', default=[100,100])
    fcP.add_argument('--bn', action='store_true')
    convP = subparsers.add_parser('conv')
    convP.add_argument('--nHidden', type=int, default=50)
    convP.add_argument('--bn', action='store_true')
    spOptnetEqP = subparsers.add_parser('spOptnetEq')
    spOptnetEqP.add_argument('--Qpenalty', type=float, default=0.1)
    optnetEqP = subparsers.add_parser('optnetEq')
    optnetEqP.add_argument('--Qpenalty', type=float, default=0.1)
    optnetIneqP = subparsers.add_parser('optnetIneq')
    optnetIneqP.add_argument('--Qpenalty', type=float, default=0.1)
    optnetIneqP.add_argument('--nineq', type=int, default=100)
    optnetLatent = subparsers.add_parser('optnetLatent')
    optnetLatent.add_argument('--Qpenalty', type=float, default=0.1)
    optnetLatent.add_argument('--nLatent', type=int, default=100)
    optnetLatent.add_argument('--nineq', type=int, default=100)
    args = parser.parse_args()

    args.cuda = not args.no_cuda and torch.cuda.is_available()
    t = '{}.{}'.format(args.boardSz, args.model)
    # print(t)
    if args.model == 'optnetEq' or args.model == 'spOptnetEq':
        t += '.Qpenalty={}'.format(args.Qpenalty)
    elif args.model == 'optnetIneq':
        t += '.Qpenalty={}'.format(args.Qpenalty)
        t += '.nineq={}'.format(args.nineq)
    elif args.model == 'optnetLatent':
        t += '.Qpenalty={}'.format(args.Qpenalty)
        t += '.nLatent={}'.format(args.nLatent)
        t += '.nineq={}'.format(args.nineq)
    elif args.model == 'fc':
        t += '.nHidden:{}'.format(','.join([str(x) for x in args.nHidden]))
        if args.bn:
            t += '.bn'
    if args.save is None:
        args.save = os.path.join(args.work, t)
    setproctitle.setproctitle('bamos.sudoku.' + t)

    with open('data/{}/features.pt'.format(args.boardSz), 'rb') as f:
        X = torch.load(f)
    with open('data/{}/labels.pt'.format(args.boardSz), 'rb') as f:
        Y = torch.load(f)

    N, nFeatures = X.size(0), int(np.prod(X.size()[1:]))

    nTrain = int(N*(1.-args.testPct))
    nTest = N-nTrain

    trainX = X[:nTrain]
    trainY = Y[:nTrain]
    testX = X[nTrain:]
    testY = Y[nTrain:]

    assert(nTrain % args.batchSz == 0)
    assert(nTest % args.testBatchSz == 0)

    save = args.save
    if os.path.isdir(save):
        shutil.rmtree(save)
    os.makedirs(save)

    npr.seed(1)

    print_header('Building model')
    if args.model == 'fc':
        nHidden = args.nHidden
        model = models.FC(nFeatures, nHidden, args.bn)
    elif args.model == 'conv':
        model = models.Conv(args.boardSz)
    elif args.model == 'optnetEq':
        model = models.OptNetEq(args.boardSz, args.Qpenalty, trueInit=False)
    elif args.model == 'spOptnetEq':
        model = models.SpOptNetEq(args.boardSz, args.Qpenalty, trueInit=False)
    elif args.model == 'optnetIneq':
        model = models.OptNetIneq(args.boardSz, args.Qpenalty, args.nineq)
    elif args.model == 'optnetLatent':
        model = models.OptNetLatent(args.boardSz, args.Qpenalty, args.nLatent, args.nineq)
    else:
        assert False

    if args.cuda:
        model = model.cuda()

    fields = ['epoch', 'loss', 'err']
    trainF = open(os.path.join(save, 'train.csv'), 'w')
    trainW = csv.writer(trainF)
    trainW.writerow(fields)
    trainF.flush()
    fields = ['epoch', 'loss', 'err']
    testF = open(os.path.join(save, 'test.csv'), 'w')
    testW = csv.writer(testF)
    testW.writerow(fields)
    testF.flush()


    if 'optnet' in args.model:
        # if args.tvInit: lr = 1e-4
        # elif args.learnD: lr = 1e-2
        # else: lr = 1e-3
        lr = 1e-1
    else:
        lr = 1e-3
    optimizer = optim.Adam(model.parameters(), lr=lr)

    # writeParams(args, model, 'init')
    test(args, 0, model, testF, testW, testX, testY)
    for epoch in range(1, args.nEpoch+1):
        # update_lr(optimizer, epoch)
        train(args, epoch, model, trainF, trainW, trainX, trainY, optimizer)
        test(args, epoch, model, testF, testW, testX, testY)
        torch.save(model, os.path.join(args.save, 'latest.pth'))
        # writeParams(args, model, 'latest')
        os.system('./plot.py "{}" &'.format(args.save))
    print(model.A)

def writeParams(args, model, tag):
    if args.model == 'optnet':
        A = model.A.data.cpu().numpy()
        np.savetxt(os.path.join(args.save, 'A.{}'.format(tag)), A)

def train(args, epoch, model, trainF, trainW, trainX, trainY, optimizer):
    batchSz = args.batchSz

    batch_data_t = torch.FloatTensor(batchSz, trainX.size(1), trainX.size(2), trainX.size(3))
    batch_targets_t = torch.FloatTensor(batchSz, trainY.size(1), trainX.size(2), trainX.size(3))
    if args.cuda:
        batch_data_t = batch_data_t.cuda()
        batch_targets_t = batch_targets_t.cuda()
    batch_data = Variable(batch_data_t, requires_grad=False)

    batch_targets = Variable(batch_targets_t, requires_grad=False)
    for i in range(0, trainX.size(0), batchSz):
        batch_data.data[:] = trainX[i:i+batchSz]
        batch_targets.data[:] = trainY[i:i+batchSz]
        # Fixed batch size for debugging:
        # batch_data.data[:] = trainX[:batchSz]
        # batch_targets.data[:] = trainY[:batchSz]

        optimizer.zero_grad()
        preds = model(batch_data)
        loss = nn.MSELoss()(preds, batch_targets)
        loss.backward()
        optimizer.step()
        #print(preds.data) ## self added
        err = computeErr(preds.data)/batchSz
        print('Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.4f} Err: {:.4f}'.format(
            epoch, i+batchSz, trainX.size(0),
            float(i+batchSz)/trainX.size(0)*100,
            loss.data, err))

        trainW.writerow((epoch-1+float(i+batchSz)/trainX.size(0), loss.data, err))
        trainF.flush()

def test(args, epoch, model, testF, testW, testX, testY):
    batchSz = args.testBatchSz

    test_loss = 0
    batch_data_t = torch.FloatTensor(batchSz, testX.size(1), testX.size(2), testX.size(3))
    batch_targets_t = torch.FloatTensor(batchSz, testY.size(1), testX.size(2), testX.size(3))
    if args.cuda:
        batch_data_t = batch_data_t.cuda()
        batch_targets_t = batch_targets_t.cuda()
    with torch.no_grad():
        batch_data = batch_data_t
        batch_targets = batch_targets_t

    nErr = 0
    for i in range(0, testX.size(0), batchSz):
        print('Testing model: {}/{}'.format(i, testX.size(0)), end='\r')
        batch_data.data[:] = testX[i:i+batchSz]
        batch_targets.data[:] = testY[i:i+batchSz]
        output = model(batch_data)

        test_loss += nn.MSELoss()(output, batch_targets)
        nErr += computeErr(output.data)
        print(nErr)
    nBatches = testX.size(0)/batchSz
    print(test_loss.data)
    test_loss = test_loss.data/nBatches
    test_err = nErr/testX.size(0)
    print('TEST SET RESULTS:' + ' ' * 20)
    print('Average loss: {:.4f}'.format(test_loss))
    print('Err: {:.4f}'.format(test_err))

    testW.writerow((epoch, test_loss, test_err))
    testF.flush()

def computeErr(pred):
    batchSz = pred.size(0)
    nsq = int(pred.size(1))
    n = int(np.sqrt(nsq))
    s = (nsq-1)*nsq//2 # 0 + 1 + ... + n^2-1
    I = torch.max(pred, 3)[1].squeeze().view(batchSz, nsq, nsq)
    #print("I is \n") ## self added
    #print(I) ## self added

    def invalidGroups(x):
        valid = (x.min(1)[0] == 0)
        valid *= (x.max(1)[0] == nsq-1)
        valid *= (x.sum(1) == s)
        return 1-valid

    boardCorrect = torch.ones(batchSz).type_as(pred)
    for j in range(nsq):
        # Check the jth row and column.
        boardCorrect[invalidGroups(I[:,j,:])] = 0
        boardCorrect[invalidGroups(I[:,:,j])] = 0

        # Check the jth block.
        row, col = n*(j // n), n*(j % n)
        M = invalidGroups(I[:,row:row+n,col:col+n].contiguous().view(batchSz,-1))
        boardCorrect[M] = 0

        if boardCorrect.sum() == 0:
            return batchSz

    return batchSz-boardCorrect.sum()

if __name__=='__main__':
    main()
