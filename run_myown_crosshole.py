# Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.


from estimater import *
from datareader import *
import argparse
import os
import cv2


if __name__=='__main__':
  parser = argparse.ArgumentParser()
  code_dir = os.path.dirname(os.path.realpath(__file__))
  parser.add_argument('--mesh_file', type=str, default=f'{code_dir}/demo_data/mustard0/mesh/textured_simple.obj')
  parser.add_argument('--test_scene_dir', type=str, default=f'{code_dir}/demo_data/mustard0')
  parser.add_argument('--est_refine_iter', type=int, default=5)
  parser.add_argument('--track_refine_iter', type=int, default=2)
  parser.add_argument('--debug', type=int, default=1)
  parser.add_argument('--debug_dir', type=str, default=f'{code_dir}/debug')
  args = parser.parse_args()

  set_logging_format()
  set_seed(0)

  mesh_file = "/home/rp/nisara/myFoundationPose/FoundationPose/demo_data/cross_hole/mesh/cross_hole.obj"
  test_scene_dir = "/home/rp/nisara/myFoundationPose/FoundationPose/demo_data/cross_hole"

  mesh = trimesh.load(mesh_file)

  debug = args.debug
  debug_dir = args.debug_dir
  os.system(f'rm -rf {debug_dir}/* && mkdir -p {debug_dir}/track_vis {debug_dir}/ob_in_cam')

  to_origin, extents = trimesh.bounds.oriented_bounds(mesh)
  bbox = np.stack([-extents/2, extents/2], axis=0).reshape(2,3)

  scorer = ScorePredictor()
  refiner = PoseRefinePredictor()
  glctx = dr.RasterizeCudaContext()
  est = FoundationPose(model_pts=mesh.vertices, model_normals=mesh.vertex_normals, mesh=mesh, scorer=scorer, refiner=refiner, debug_dir=debug_dir, debug=debug, glctx=glctx)
  logging.info("estimator initialization done")

  reader = YcbineoatReader(video_dir=test_scene_dir, shorter_side=None, zfar=np.inf)

  ## Save the video
  img = cv2.imread(reader.color_files[0])
  height, width, channels = img.shape
  fourcc = cv2.VideoWriter_fourcc(*'mp4v')
  out = cv2.VideoWriter('output4.mp4', fourcc, 30.0, (width, height))

  for i in range(len(reader.color_files)):
    logging.info(f'i:{i}')
    color = reader.get_color(i)
    depth = reader.get_depth(i)
    ## We gotta register each time, since there is no pose tracking
    if i == 0:
      first = True
    else:
      first = False
    mask = reader.get_mask(0).astype(bool)
    pose = est.calculatePoseEachTime(K=reader.K, rgb=color, depth=depth, ob_mask=mask, first=first, iteration=args.est_refine_iter)

    if debug>=3:
        m = mesh.copy()
        m.apply_transform(pose)
        m.export(f'{debug_dir}/model_tf.obj')
        xyz_map = depth2xyzmap(depth, reader.K)
        valid = depth>=0.1
        pcd = toOpen3dCloud(xyz_map[valid], color[valid])
        o3d.io.write_point_cloud(f'{debug_dir}/scene_complete.ply', pcd)

    os.makedirs(f'{debug_dir}/ob_in_cam', exist_ok=True)
    np.savetxt(f'{debug_dir}/ob_in_cam/{reader.id_strs[i]}.txt', pose.reshape(4,4))

    if debug>=1:
      # center_pose = pose@np.linalg.inv(to_origin)
      center_pose = pose
      vis = draw_posed_3d_box(reader.K, img=color, ob_in_cam=center_pose, bbox=bbox)
      vis = draw_xyz_axis(color, ob_in_cam=center_pose, scale=0.1, K=reader.K, thickness=3, transparency=0, is_input_rgb=True)
      cv2.imshow('1', vis[...,::-1])
      cv2.waitKey(1) # Wait indefinitely until a key is pressed
      # filepath = reader.color_files[i]
      # dirpath, imagena = os.path.split(filepath)
      # imagename, ext = os.path.splitext(imagena)
      # o_image_path = os.path.join(dirpath + "/poses/", imagename + "_pose" + ext)
      o_image_path = reader.color_files[i].replace('rgb','poses3')
      print(o_image_path)
      cv2.imwrite(o_image_path , vis)
      out.write(vis)


    if debug>=2:
      os.makedirs(f'{debug_dir}/track_vis', exist_ok=True)
      imageio.imwrite(f'{debug_dir}/track_vis/{reader.id_strs[i]}.png', vis)



## How is obs_in_cams rotation calculated?
# The z-axis of the camera's coordinate system is calculated as the negative of the position of the camera. This ensures that the camera is always looking towards the origin of the object's coordinate system.
# The x-axis of the camera's coordinate system is calculated as the cross product of the up direction (the positive z-axis) and the z-axis. If the cross product is zero (which can happen if the up direction and the z-axis are parallel), the x-axis is set to the positive x-axis.
# The y-axis of the camera's coordinate system is calculated as the cross product of the z-axis and the x-axis.

