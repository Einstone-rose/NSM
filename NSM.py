# -*- coding: utf-8 -*-
# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:light
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.4'
#       jupytext_version: 1.2.1
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# + {"heading_collapsed": true, "cell_type": "markdown"}
# ## Dependencies

# + {"hidden": true}
import torch
import torch.nn as nn
import torch.nn.functional as F

# + {"hidden": true}
from random import randint
from itertools import permutations

# + {"heading_collapsed": true, "cell_type": "markdown"}
# ## Hyperparams

# + {"hidden": true}
EMBD_DIM = 7
OUT_DIM = 4
BATCH = 32
N = 3


# + {"heading_collapsed": true, "cell_type": "markdown"}
# # Concept Vocabulary

# + {"hidden": true}
def to_glove(token):
    return torch.rand(EMBD_DIM)


# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ### Dummy data

# + {"hidden": true}
property_types = ['color', 'material']

property_concepts = {
    'color': ['red', 'green', 'blue'],
    'material': ['cloth', 'rubber']
}

state_identities = ['cat', 'shirt']

relationships = ['holding', 'behind']

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ## Preparation

# + {"hidden": true}
# each property has a type
L = len(property_types)

# we add identity and relations in idx 0 and L+1 respectively (TODO: with those names?)
property_types = ['identity'] + property_types
property_types += ['relations']
property_concepts['identity'] = state_identities
property_concepts['relations'] = relationships

D = torch.stack([to_glove(property_type) for property_type in property_types])

# + {"hidden": true}
# each property has a series of concepts asociated
# ordered_C is separated by property, C includes all concepts.
ordered_C = [
    torch.stack([to_glove(concept) for concept in property_concepts[property]])
    for property in property_types
]
C = torch.cat(ordered_C, dim=0)

# we add c' for non structural words (@ idx -1)
# TODO: c' initialization?
c_prime = torch.rand(1, EMBD_DIM, requires_grad=True)
C = torch.cat([C, c_prime], dim=0)

# + {"heading_collapsed": true, "cell_type": "markdown"}
# # Scene Graph

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ### Dummy data

# + {"hidden": true}
nodes = ['kitten', 'person', 'shirt']

relations = {
    ('person', 'shirt'): 'wear',
    ('person', 'kitten'): 'holding',
    ('kitten', 'shirt'): 'bite'
}

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ## Preparation

# + {"hidden": true}
# for simplicity: random state initialization of properties (TODO)
S = torch.rand(BATCH, len(nodes), L+1, EMBD_DIM)

# + {"hidden": true}
# build adjacency matrix (TODO: now all graphs are same)
# the edge features e' are inserted into an adjacency matrix for eficiency
adjacency_mask = torch.zeros(BATCH, len(nodes), len(nodes))
E = torch.zeros(BATCH, len(nodes), len(nodes), EMBD_DIM)
for idx_pair in permutations(range(len(nodes)), 2):
    pair = tuple(nodes[idx] for idx in idx_pair)
    if pair in relations:
        E[:,idx_pair[0],idx_pair[1]] = torch.rand(EMBD_DIM)   # (TODO)
        adjacency_mask[:,idx_pair[0],idx_pair[1]] = 1

# + {"hidden": true}
# alternatively we can use hybrid (sparse + dense) tensors to reduce memory and computation overhead
indices = []
values = []
for idx_pair in permutations(range(len(nodes)), 2):
    pair = tuple(nodes[idx] for idx in idx_pair)
    if pair in relations:
        indices.append(idx_pair)
        values.append(torch.rand(EMBD_DIM))

sparse_adj = torch.sparse.FloatTensor(
    torch.LongTensor(indices).t(), 
    torch.stack(values),
    (len(nodes), len(nodes), EMBD_DIM)
)

E_sparse = torch.stack([sparse_adj for _ in range(BATCH)])

# + {"hidden": true}
E_sparse.shape == E.shape

# + {"heading_collapsed": true, "cell_type": "markdown"}
# # Reasoning Instructions


# + {"hidden": true}
# the tokenized question w/o punctuation
questions = [['what', 'color', 'is', 'the', 'cat'] for _ in range(BATCH)]

# + {"hidden": true}
# embedded questions, shape [batch, len_question, embd_dim]
embd_questions = torch.stack([
    torch.stack([to_glove(word) for word in question])
    for question in questions
])

# + {"hidden": true}
# bilinear proyecction initialized to identity
W = torch.eye(EMBD_DIM, requires_grad=True)

# TODO: check if can move transpose to definition
P_i = torch.bmm(
    torch.bmm(
        embd_questions,
        W.expand(BATCH, EMBD_DIM, EMBD_DIM)
    ),
    C.expand(BATCH, -1, EMBD_DIM).transpose(1,2)
)
P_i = torch.softmax(P_i, dim=2)

# + {"hidden": true}
# weighted sum, but using w_i instead of c' (if it does not match any of the concepts closely enough--> use w_i)
V = (P_i[:, :, -1]).unsqueeze(2) * embd_questions + torch.bmm(
    P_i[:, :, :-1], C[:-1, :].expand(BATCH, -1, EMBD_DIM))

# + {"hidden": true}
# encoder is lstm (TODO: one direction?)
encoder_lstm = nn.LSTM(input_size=EMBD_DIM, hidden_size=EMBD_DIM, batch_first=True, bidirectional=False)

# run encoder on normalized sequence
_, encoder_hidden = encoder_lstm(V)
(q, _) = encoder_hidden
q = q.view(BATCH, 1, EMBD_DIM)

# + {"hidden": true}
# recurrent decoder (TODO: LSTM?, we know nothing of decoder)
decoder_lstm = nn.LSTM(input_size=EMBD_DIM, hidden_size=EMBD_DIM, batch_first=True, bidirectional=False)

# run decoder
h, _ = decoder_lstm(q.expand(BATCH, N+1, EMBD_DIM), encoder_hidden)

# + {"hidden": true}
# obtain r (reasoning instructions) by expressing each h_i as a pondered sum of V
r = torch.bmm(torch.softmax(torch.bmm(h, V.transpose(1, 2)), dim=2), V)

# + {"heading_collapsed": true, "cell_type": "markdown"}
# # Model Simulation
#
#

# + {"hidden": true}
# initial p_0 is uniform over states
p_i = torch.ones(BATCH, len(nodes)) / len(nodes)

# + {"hidden": true, "cell_type": "markdown"}
# (everything below is inside recurrent loop)
#
# ~~~python
# for i in range(N):
#     MODEL SIMULATION
# ~~~

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ## $R_i$

# + {"hidden": true}
# for the ith recurrent step... 
i=0

# the appropiate reasoning instruction for the ith step
r_i = r[:,i,:]

# + {"hidden": true}
R_i = F.softmax(torch.bmm(
    D.expand(BATCH, -1, EMBD_DIM),
    r_i.unsqueeze(2)
), dim=1).squeeze(2)

# "degree to which that reasoning instruction is concerned with semantic relations"
r_i_prime = R_i[:,-1].unsqueeze(1)
property_R_i = R_i[:,:-1]

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ## $𝛾_i_s$
#
# $$
#     \sigma \left( \sum_{j=0}^L R_i(j)(r_i \circ W_j s^j) \right)
# $$

# + {"hidden": true}
# bilinear proyecctions (one for each property) initialized to identity.
property_W = torch.stack([torch.eye(EMBD_DIM, requires_grad=True) for _ in range(L + 1)], dim=0)

𝛾_i_s = F.elu(torch.sum(
    torch.mul(
        property_R_i.view(BATCH, -1, 1, 1),
        torch.mul(
            torch.matmul(
                S.transpose(2,1), 
                property_W
            ), r_i.view(BATCH, 1, 1, EMBD_DIM)
        )
    ), dim=1
))

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# #### Alternative

# + {"code_folding": [], "hidden": true}
# stacked_properties = []
# for property_idx in range(L + 1):
#     stacked_properties.append(
#         torch.mul(
#             torch.mul(
#                 r_i.unsqueeze(1),
#                 torch.bmm(
#                     S[:, :, property_idx, :],
#                     property_W[property_idx].expand(BATCH, EMBD_DIM, EMBD_DIM))),
#             property_R_i[:, property_idx].view(BATCH, 1, -1).expand(BATCH, 1, EMBD_DIM)))

# alt_𝛾_i_s = F.elu(torch.sum(torch.stack(stacked_properties, dim=2), dim=2))
# assert (alt_𝛾_i_s == 𝛾_i_s).all()

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ## $𝛾_i_e$
# $$
#     \sigma \left( r_i \circ W_{L+1} e' \right)
# $$

# + {"hidden": true}
# bilinear proyecction initialized to identity.
W_L_plus_1 = torch.eye(EMBD_DIM, requires_grad=True)

𝛾_i_e = F.elu(
    torch.mul(torch.bmm(
            E.view(BATCH, -1, EMBD_DIM), 
            W_L_plus_1.expand(BATCH, EMBD_DIM, EMBD_DIM)
        ), r_i.unsqueeze(1))
).view(BATCH, len(nodes), len(nodes), EMBD_DIM)

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ## $p_i^r$
#
# $$
# softmax_{s \in S}\left(W_r \cdot\sum_{(s', s) \in E} p_i(s') \cdot \gamma_i((s', s))\right)
# $$

# + {"hidden": true}
W_r = nn.Linear(EMBD_DIM, 1, bias=False)

p_i_r = F.softmax(
    W_r(
        torch.sum(
            torch.mul(
                𝛾_i_e,
                p_i.view(BATCH, -1, 1, 1)
            ), dim=1)).squeeze(2), dim=1)

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# #### Alternative
#
# To check equivalency between matrix computation and math.

# + {"hidden": true}
# # adjacency matrix
# adj = 𝛾_i_e.sum(dim=3) > 0
# adj[0]

# + {"hidden": true}
# batch, height, width, dim = 𝛾_i_e.shape

# all_batch = []
# for batch_idx in range(batch):
#     all_nodes = []
#     for x in range(width):
#         weighted_sum = torch.zeros(dim)
#         for y in range(height):
#             if adj[batch_idx, y, x]:  # (s', s) \in E
#                 weighted_sum += p_i[batch_idx, y] * 𝛾_i_e[batch_idx, y, x]    # \sum
#         all_nodes.append(
#             W_r(weighted_sum).squeeze(0)
#         )
#     all_batch.append(torch.stack(all_nodes, dim=0))
# alt_p_i_r = F.softmax(torch.stack(all_batch, dim=0), dim=1)

# assert (p_i_r == alt_p_i_r).all()

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ## $p_i^s$
#
# $$
# softmax_{s \in S}(W_s \cdot \gamma_i(s))
# $$

# + {"hidden": true}
# update state probabilities (property lookup)
W_s = nn.Linear(EMBD_DIM, 1, bias=False)

p_i_s = F.softmax(W_s(𝛾_i_s).squeeze(2), dim=1)

# + {"heading_collapsed": true, "hidden": true, "cell_type": "markdown"}
# ## $p_i$
#
# $$
# r_i' \cdot p_i^r + (1 - r_i') \cdot p_i^s
# $$

# + {"hidden": true}
p_i = r_i_prime * p_i_r + (1 - r_i_prime) * p_i_s
# -

# # Final clasifier
#
# (outside recurrent loop)

# +
# Sumarize final NSM state
r_N = r[:,N,:]
property_R_N = F.softmax(torch.bmm(
    D.expand(BATCH, -1, EMBD_DIM),
    r_N.unsqueeze(2)
), dim=1).squeeze(2)[:,:-1]

# equivalent to:torch.sum(p_i.unsqueeze(2) * torch.sum(property_R_N.view(10, 1, 3, 1) * S, dim=2), dim=1)
m = torch.bmm(
    p_i.unsqueeze(1),
    torch.sum(property_R_N.view(BATCH, 1, L+1, 1) * S, dim=2)
)

# +
# final classifier (TODO: hidden dims ???)
classifier = nn.Sequential(nn.Linear(2*EMBD_DIM, 2*EMBD_DIM),
                           nn.ELU(),
                           nn.Linear(2*EMBD_DIM, OUT_DIM))

pre_logits = classifier(torch.cat([m, q], dim=2).squeeze(1))
# -

pre_logits.shape

L+1


