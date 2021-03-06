import os
import math
import torch
import torch.nn as nn
import torch.optim as optim
import matplotlib.pyplot as plt
from tqdm import tqdm
import numpy as np
import argparse
import random

from dataset import *
from constants import *
from util import *
from model import DeepJ
from generate import Generation
from midi_io import save_midi

criterion = nn.CrossEntropyLoss()

def plot_loss(training_loss, validation_loss, name):
    # Draw graph
    plt.clf()
    plt.plot(training_loss)
    plt.plot(validation_loss)
    plt.savefig(OUT_DIR + '/' + name)

def train(model, train_batcher, train_len, val_batcher, val_len, optimizer, plot=True, gen_rate=1, patience=5):
    """
    Trains a model on multiple seq batches by iterating through a generator.
    """
    # Number of training steps per epoch
    epoch = 1
    total_step = 1

    # Keep tracks of all losses in each epoch
    train_losses = []
    val_losses = []

    # Epoch loop
    while True:
        # Training
        step = 1
        total_loss = 0

        with tqdm(range(train_len)) as t:
            t.set_description('Epoch {}'.format(epoch))
            
            for _ in t:
                data = train_batcher()
                loss = train_step(model, data, optimizer)

                total_loss += loss
                avg_loss = total_loss / step
                t.set_postfix(loss=avg_loss)

                step += 1
                total_step += 1

        train_losses.append(avg_loss)

        # Validation
        step = 1
        total_loss = 0

        v_gen = val_batcher()

        with tqdm(range(val_len)) as t:
            t.set_description('Validation {}'.format(epoch))

            for _ in t:
                data = val_batcher()
                loss = val_step(model, data)
                total_loss += loss
                avg_loss = total_loss / step
                t.set_postfix(loss=avg_loss)
                step += 1
            
        val_losses.append(avg_loss)

        if plot:
            plot_loss(train_losses, val_losses, 'loss.png')

        # Save model
        torch.save(model.state_dict(), OUT_DIR + '/model_' + str(epoch) + '.pt')

        # Generate
        if gen_rate > 0 and epoch % gen_rate == 0:
            print('Generating...')
            Generation(model).export(name='epoch_' + str(epoch))

        epoch += 1

        # Early stopping
        """
        if epoch > patience:
            min_loss = min(val_losses)
            if min(val_losses[-patience:]) > min_loss:
                break
        """

def train_step(model, data, optimizer):
    """
    Trains the model on a single batch of sequence.
    """
    model.train()

    # Zero out the gradient
    optimizer.zero_grad()

    loss, avg_loss = compute_loss(model, data)

    loss.backward()

    # `clip_grad_norm` helps prevent the exploding gradient problem in RNNs / LSTMs.
    # Reference: https://github.com/pytorch/examples/blob/master/word_language_model/main.py
    torch.nn.utils.clip_grad_norm(model.parameters(), GRADIENT_CLIP)

    optimizer.step()

    return avg_loss

def val_step(model, data):
    model.eval()
    return compute_loss(model, data, volatile=True)[1]

def compute_loss(model, data, volatile=False):
    """
    Trains the model on a single batch of sequence.
    """
    # Convert all tensors into variables
    note_seq, styles = data
    styles = var(one_hot_batch(styles, NUM_STYLES), volatile=volatile)
    
    # Feed it to the model
    inputs = var(one_hot_seq(note_seq[:, :-1], NUM_ACTIONS), volatile=volatile)
    targets = var(note_seq[:, 1:], volatile=volatile)
    output, _ = model(inputs, styles, None)

    # Compute the loss.
    loss = criterion(output.view(-1, NUM_ACTIONS), targets.view(-1))

    return loss, loss.data[0]

def main():
    parser = argparse.ArgumentParser(description='Trains model')
    parser.add_argument('--path', help='Load existing model?')
    parser.add_argument('--gen', default=0, type=int, help='Generate per how many epochs?')
    parser.add_argument('--noplot', default=False, action='store_true', help='Do not plot training/loss graphs')
    args = parser.parse_args()

    print('=== Loading Model ===')
    print('GPU: {}'.format(torch.cuda.is_available()))
    model = DeepJ()

    if torch.cuda.is_available():
        model.cuda()

    if args.path:
        model.load_state_dict(torch.load(args.path))
        print('Restored model from checkpoint.')

    # Construct optimizer
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)

    print()

    print('=== Dataset ===')
    os.makedirs(OUT_DIR, exist_ok=True)
    print('Loading data...')
    data = process(load())
    print()
    print('Creating data generators...')
    train_data, val_data = validation_split(data)
    train_batcher = batcher(sampler(train_data))
    val_batcher = batcher(sampler(val_data))

    """
    # Checks if training data sounds right.
    for i, (train_seq, *_) in enumerate(train_batcher()):
        save_midi('train_seq_{}'.format(i), train_seq[0].cpu().numpy())
    """

    print('Training Sequences:', len(train_data[0]), 'Validation Sequences:', len(val_data[0]))
    print()

    print('=== Training ===')
    train(model, train_batcher, TRAIN_CYCLES, val_batcher, VAL_CYCLES, optimizer, plot=not args.noplot, gen_rate=args.gen)

if __name__ == '__main__':
    main()
