---
title: "GSoC'19: Duckietown.jl Summary"
date:   2019-08-24 16:00 +0530
categories: GSoC19
---

Hello there,

Over the past year, I continued my streak with Julia by contributing to [some interesting experiments](https://fluxml.ai/2019/03/05/dp-vs-rl.html) with [differentiable programming](https://fluxml.ai/2019/02/07/what-is-differentiable-programming.html). That got me super-excited about the paradigm of differentiable learning. The main idea being that if we know the system, it could be used to simplify and accelerate the training process. Together with Mike and Avik, we planned on a mission: a self-driving car simulator using differentiable programming.  

We chose duckietown environment to test our approach. [Duckietown](https://www.duckietown.org) is a project started by Prof. Liam Paull. It is a miniature model of a town having buildings, vehicles, traffic signals, and pedestrians. Maxime Chevalier-Boisvert et al, from MILA, have built an awesome simulator of the duckietown, called [gym-duckietown](https://github.com/duckietown/gym-duckietown). It is used for testing algorithms before deploying it in real duckietown environment. But since it is written using python, it is not differentiable. Hence to make it differentiable we had to build it in julia.

[Duckietown.jl](https://github.com/tejank10/Duckietown.jl) creation is spread over three parts:
- The Simulator
- Rendering with RayTracer
- Training

Let's get started!

## The Environment
Duckietown environment contains maps for different tasks - straight road, loop, zigzag turns, UdeM, etc. There are also some variants of these maps with dynamic objects, like traffic signal and pedestrians. The maps are encoded in a .yaml files and can be parsed with [YAML.jl](https://github.com/BioJulia/YAML.jl). Each environment contains a map in the form of a grid. Each element of the grid is allocated a tile: for eg., a road, an asphalt, an office floor or it can be a grassy surface. A logical arrangement of these tiles is all that is required for a bare-bones version of the map to set up. That’s all the straight road and loopy road maps have. To make these maps more challenging, we need to add objects to it. Objects can be static or dynamic. Static objects include house, tree, traffic sign, bus, truck, traffic cone, etc. Dynamic objects are traffic signals and duckies which are the pedestrians in the duckietown. The positions of these objects are defined in the map. An object is represented as meshes, with texture wrapped around it.  

<img src="https://github.com/tejank10/tejank10.github.io/raw/master/assets/udem1.gif" alt="UdeM" align="middle" width="400" height="300"/>

## The Simulator
```julia
using Duckietown, Flux, Zygote

sim = Simulator(map_name="straight_road", camera_width = 128, camera_height = 128)
```
Simulator manages the subtasks involved in running the duckietown and maintains related statistics. The subtasks include updating the states and positions of different objects involved, running an action on duckiebot, maintaining data such as velocity, position, the action performed on the duckiebot, rendering what the bit sees, etc. The parameters of the simulator are defined in a `FixedParams` object. These are the parameters that define the behavior of the simulator.

## Rendering the view
`rende_obs(...)` is used to render was duckiebot sees. We use differentiable [RayTracer.jl](https://github.com/avik-pal/RayTracer.jl) for this purpose. For rendering, we first need to define a camera model. The camera needs to know where the bot is looking from & at, dimensions of the image, field of view, focal length, and up vector.
```julia
x, y, z = sim.cur_pos
# get the direction in which bot is looking
dx, dy, dz = get_dir_vec(sim.cur_angle)

## Define camera model
# Looking from
eye = Vec3([x], [y], [z])
# Looking at
target = Vec3([x + dx], [y + dy], [z + dz])
# vup is vector pointing in upward direction
vup = Vec3([0f0], [1f0], [0f0])
cam = Camera(eye, target, vup, cam_fov_y, focal_length, cam_width, cam_height)
```
A scene is generated containing all the objects in the environments. These objects are decomposed into triangles.
```julia
## Scene generation
scene = Vector{Triangle}()
# Decompose the objects into triangles
obj_Δs = map(obj->render(obj, fp.draw_bbox), objs)

for oΔ in obj_Δs
    scene = vcat(scene, oΔ)
end
```

Light source and its position is defined, which is then used to raytrace the scene.
```julia
# Define light source
light_pos = Vec3([-40f0], [200f0], [100f0])
# PointLight takes color, intensity and position of light source as args
light = PointLight(Vec3([1f0]), 5f15, light_pos)
origin, direction = get_primary_rays(cam)

# Rendering what duckiebot sees
im = raytrace(origin, direction, observation, light, origin, 2)
```

## Taking action
`step!(...)` is used to take action on the duckiebot. action is a vector of length 2. It specifies the speed of the left and the right wheel. each element belongs to [-1, 1], where positive speed implies moving in the forward direction. Velocities of both the wheels give us the information about the steering direction of the robot. For eg: to move on a straight road both the velocities should be equal, whereas to take a left turn velocity of the left wheel should be less than that of the right wheel. Using this, the robot’s new position and direction is calculated.  

A path to be followed is determined by bezier curves. Each tile has its bezier curve defined. For example, a straight road tile would have a straight line as its curve whereas that for a left turn would be approximately circular. Based on this curve, two kinds of rewards are defined. The distance from the curve and angular distance from the tangent of the curve. There is also a penalty to prevent a collision. Each object has a safety circle surrounding itself. Collision penalty is the degree of overlap between the safety circle of the bot and that of an object.  

With these details, we are now equipped to train a model!  


## Training a model
We define a simple Flux model, which extracts features from the image using `Conv` and passes them onto the FC layers.
```julia
# model: Input- Rendering of what duckiebot sees
#        Output- Action to be taken
model = Chain(
           Conv((3, 3), 3=>8, relu, pad = 1),
           MaxPool((2, 2)),
           Conv((3, 3), 8=>16, relu, pad = 1),
           MaxPool((2, 2)),
           Conv((3, 3), 16=>32, relu, pad = 1),
           x -> reshape(x, :, 1),
           Dense((32 * 32 * 32), 64, relu),
           Dense(64, 16, relu),
           Dense(16, 2),
           x -> reshape(x, 2))

opt = ADAM(0.001f0)
```
We begin with dividing an episode into sequences. Let’s call a sequence as `μEpisode`. In each `μEpisode`, actions are performed for a short number of timesteps. We take the loss as negative of reward and add an action penalty. Recall that actions should lie in [-1, 1]. Since for initial few timesteps actions could arbitrarily lie anywhere in the real domain, this penalty is required. Also, the reward is proportional to speed. If Very high action is chosen, then it should also set very high speed and in turn very high reward, which is not expected ideally. Action penalty is somewhat similar to the regularisation loss.

```
function μEpisode(model, sim, initial_render, μEp_len)
    obs, action, reward, done, info = step!(sim, model(initial_render))
    loss = -reward + action_penalty(action)

    done && return loss

    for iter in 2:μEp_len
        obs, action, reward, done, info = step!(sim, model(obs))
        loss += -reward + action_penalty(action)
        done && return loss
    end

    return loss
end
```
In the `episode!(...)` function, the gradient of the loss wrt to the parameters of the `model` is taken using [Zygote.jl](https://github.com/FluxML/Zygote.jl) a source-to-source AD package. Gradients are clamped to prevent the overflow due to gradient explosion.  
```
function episode!(sim)    
    for μEp in 1:NUM_μEPISODES
        # Get the gradients of μEpisode
        initial_render = render_obs(sim)
        gs = Zygote.gradient(params(model)) do
            μEpisode(model, sim, initial_render, μEPISODE_LENGTH)
        end

        # Update the weights
        for p in params(model)
            clamp!(gs[p], -0.01f0, 0.01f0)
            Flux.Optimise.update!(opt, p, gs[p])
        end

        sim.done && break
    end

    reset!(sim)
end
```
And after a while, you should be able to see the bot guiding itself on the lane!
<img src="https://raw.githubusercontent.com/tejank10/tejank10.github.io/master/assets/straight_road_w_text.gif" alt="Straight road" align="middle" width="400" height="300"/>


## What's next?
What a productive summer it was! With Duckietown.jl you can now research autonomous driving in Julia, and also leverage the differentiability aspect of it. I believe this is just a start for differentiable programming. By knowing the system, we can speed up the training of a model on it by leaps and bounds. In the future, I plan to:
- Transfer learning: Evaluating the performance model trained on one map by testing it on other maps.
- Defining tasks over different maps
- There has been some advances in terms of the [packages](https://phyre.ai) for physical environements for deep learning. I plan to do some experiments on that using diffferentiable programming.

## Acknowledgments
I am extremely grateful to my mentor Mike Innes for posing faith in me for this ambitious project. A huge thanks to my fellow GSoC’er Avik Pal for his amazing RayTracer, and helping me out from time to time. I would also like to thank Dhairya Gandhi for his valuable inputs, Julia Computing Bengaluru for hosting me, and Julia Computing for providing machines for training. Finally, I thank Google for providing me this amazing opportunity in being part of the mission to drive open-source culture.s
