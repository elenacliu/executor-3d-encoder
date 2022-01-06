import torch
import torch.nn as nn
import torch.nn.functional as F

from .modules import PointConvDensityNet

class PointConv(torch.nn.Module):
    def __init__(self, emb_dims=1024, input_shape="bnc", input_channel_dim=3, classifier=False, num_classes=40,
                 pretrained=None):
        super(PointConv, self).__init__()
        if input_shape not in ["bnc", "bcn"]:
            raise ValueError("Allowed shapes are 'bcn' (batch * channels * num_in_points), 'bnc' ")
        self.input_shape = input_shape
        self.emb_dims = emb_dims
        self.classifier = classifier
        self.input_channel_dim = input_channel_dim
        self.create_structure()
        if self.classifier: self.create_classifier(num_classes)

    def create_structure(self):
        # Arguments to define PointConv network using PointConvDensityNet class.
        # npoint:			number of points sampled from input.
        # nsample:			number of neighbours chosen for each point in sampled point cloud.
        # in_channel:		number of channels in input.
        # mlp:				sizes of multi-layer perceptrons.
        # bandwidth:		used to compute gaussian density.
        # group_all:		group all points from input to a single point if set to True.
        self.sa1 = PointConvDensityNet(npoint=512, nsample=32, in_channel=self.input_channel_dim,
                                       mlp=[64, 64, 128], bandwidth=0.1, group_all=False)
        self.sa2 = PointConvDensityNet(npoint=128, nsample=64, in_channel=128 + 3,
                                       mlp=[128, 128, 256], bandwidth=0.2, group_all=False)
        self.sa3 = PointConvDensityNet(npoint=1, nsample=None, in_channel=256 + 3,
                                       mlp=[256, 512, self.emb_dims], bandwidth=0.4, group_all=True)

    def create_classifier(self, num_classes):
        # These are simple fully-connected layers with batch-norm and dropouts.
        # This architecture is given by PointConv paper. Hence, I used it here as a default version.
        # This can be easily modified by overwriting this function or by using classifier.py class.
        self.fc1 = nn.Linear(self.emb_dims, 512)
        self.bn1 = nn.BatchNorm1d(512)
        self.drop1 = nn.Dropout(0.7)
        self.fc2 = nn.Linear(512, 256)
        self.bn2 = nn.BatchNorm1d(256)
        self.drop2 = nn.Dropout(0.7)
        self.fc3 = nn.Linear(256, num_classes)

    def forward(self, input_data):
        if self.input_shape == "bnc":
            input_data = input_data.permute(0, 2, 1)
        batch_size = input_data.shape[0]

        # Convert point clouds to latent features using PointConv network.
        l1_points, l1_features = self.sa1(input_data[:, :3, :], input_data[:, 3:, :])
        l2_points, l2_features = self.sa2(l1_points, l1_features)
        l3_points, l3_features = self.sa3(l2_points, l2_features)
        features = l3_features.view(batch_size, self.emb_dims)

        if self.classifier:
            # Use these features to classify the input point cloud.
            features = self.drop1(F.relu(self.bn1(self.fc1(features))))
            features = self.drop2(F.relu(self.bn2(self.fc2(features))))
            features = self.fc3(features)
            output = F.log_softmax(features, -1)
        else:
            # Return the PointConv features for the use of other higher level tasks.
            output = features

        return output
