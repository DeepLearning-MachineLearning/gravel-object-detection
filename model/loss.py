import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as f
from utils.iou import compute_giou, compute_iou


class Loss(nn.Module):
    def __init__(self, anchors, input_size):
        super(Loss, self).__init__()

        self.s_anchors, self.m_anchors, self.l_anchors = anchors

        self.input_size = torch.tensor(input_size)
        self.iou_thresh = torch.tensor(0.5)

    def forward(self, s_output, m_output, l_output, s_gt_tensor, m_gt_tensor, l_gt_tensor, s_gt_coords, m_gt_coords, l_gt_coords):
        s_giou_loss, s_conf_loss = self.compute_loss(s_output, s_gt_tensor, s_gt_coords)
        m_giou_loss, m_conf_loss = self.compute_loss(m_output, m_gt_tensor, m_gt_coords)
        l_giou_loss, l_conf_loss = self.compute_loss(l_output, l_gt_tensor, l_gt_coords)

        s_loss = s_giou_loss + s_conf_loss
        m_loss = m_giou_loss + m_conf_loss
        l_loss = l_giou_loss + l_conf_loss

        return s_loss + m_loss + l_loss

    def compute_loss(self, output, gt_tensor, gt_coords):
        output_coord = output[:, :, :, :, 0:4]
        output_conf = output[:, :, :, :, 4:5]

        gt_tensor_coord = gt_tensor[:, :, :, :, 0:4]
        gt_tensor_conf = gt_tensor[:, :, :, :, 4:5]

        giou_loss = self.compute_giou_loss(output_coord, gt_tensor_coord, gt_tensor_conf)
        conf_loss = self.compute_conf_loss(output_coord, output_conf, gt_tensor_conf, gt_coords)

        giou_loss = torch.mean(torch.sum(giou_loss, [1, 2, 3, 4]))
        conf_loss = torch.mean(torch.sum(conf_loss, [1, 2, 3, 4]))

        return giou_loss, conf_loss

    def compute_giou_loss(self, output_coord, gt_tensor_coord, gt_tensor_conf):
        giou = compute_giou(output_coord, gt_tensor_coord)[..., np.newaxis]
        box_scale = torch.div(gt_tensor_coord[:, :, :, :, 2:3] * gt_tensor_coord[:, :, :, :, 3:4], torch.pow(self.input_size, 2))
        giou_loss = gt_tensor_conf * torch.sub(2, box_scale) * torch.sub(1, giou)

        return giou_loss

    def compute_conf_loss(self, output_coord, output_conf, gt_tensor_conf, gt_coords):
        iou = compute_iou(output_coord[:, :, :, :, np.newaxis, :], gt_coords[:, np.newaxis, np.newaxis, np.newaxis, :, :])
        max_iou = torch.max(iou, dim=-1)[0][..., np.newaxis]

        # Support GPU Computation
        if max_iou.is_cuda:
            self.iou_thresh = self.iou_thresh.to(device=max_iou.device)

        background_conf = torch.sub(1, gt_tensor_conf) * torch.lt(max_iou, self.iou_thresh).float()
        conf_focal = torch.pow(gt_tensor_conf - output_conf, 2)

        conf_loss = conf_focal * (
                gt_tensor_conf * f.binary_cross_entropy_with_logits(input=gt_tensor_conf, target=self.logit(output_conf))
                +
                background_conf * f.binary_cross_entropy_with_logits(input=gt_tensor_conf, target=self.logit(output_conf))
        )

        return conf_loss

    @staticmethod
    def logit(x):
        x = torch.div(x, 1 - x)
        x = torch.log(x)
        return x
