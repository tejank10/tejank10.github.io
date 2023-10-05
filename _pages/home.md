---
title: "Tejan Karmali - Home"
layout: gridlay
excerpt: "Tejan Karmali"
sitemap: false
permalink: /
---

<div class="container-fluid">

<div class="row">

<div class="col-sm-8">

I am a computer vision researcher. Currently, I am working as a Research Engineer at [Avataar](https://avataar.ai), where I am finding solutions for image-to-3D reconstruction problem. Before that, I was a Pre-Doctoral Researcher at [Google Research India](https://research.google/teams/india-research-lab/). I worked towards solving the problem of predicting super-resolved segmentation maps from satellite imagery in the Earth Observation Science team under the guidance of [Dr. Varun Gulshan](https://sites.google.com/view/varungulshan/home) and Alex Wilson.


Previously, I graduated from the Indian Institute of Science Bengaluru ([IISc](https://www.iisc.ac.in/)) with an M.Tech. (Research) in [Computational and Data Sciences](https://cds.iisc.ac.in/). I was part of Video Analytics Lab ([VAL](https://val.cds.iisc.ac.in/)), where I worked towards my [thesis](https://etd.iisc.ac.in/handle/2005/5899) titled *Landmark Estimation and Image Synthesis Guidance using Self-Supervised Networks*, advised by [Prof. R. Venkatesh Babu](http://cds.iisc.ac.in/faculty/venky/) and [Dr. Varun Jampani](varunjampani.github.io/).


I have been fortunate to be part of Google Summer of Code twice to contribute to the [JuliaLang](https://julialang.org/) under the mentorship of [Mike Innes](https://mikeinnes.io/). In the summer of 2019, I built [Duckietown.jl](https://github.com/tejank10/Duckietown.jl), a differentiable self-driving car simulation environment that enables the training of agents using differentiable programming. While in the summer of 2018, I contributed to Flux's [model zoo](https://github.com/FluxML/model-zoo) with Reinforcement Learning algorithms and built [AlphaGo.jl](https://github.com/tejank10/AlphaGo.jl) to train and play zero-sum board games using Alpha(Go)Zero algorithm in JuliaLang.

My research interest is in creating controllable representations from generative models for downstream tasks, such as image editing, 3D reconstruction, and building robust descriptors.


<p align="center">
  <a href="mailto:tejank10@gmail.com">Email</a>  /
  <a href="./files/TejanKarmaliCV.pdf">CV</a> /
  <a href="https://scholar.google.co.in/citations?user=Ulsd7DkAAAAJ&hl=en">Google Scholar</a> /
  <a href="https://github.com/tejank10">GitHub</a> /
  <a href="https://www.linkedin.com/in/tejank10/">LinkedIn</a>
</p>

### News
{% for article in site.data.news limit:9 %}
{{ article.date }} :
<em>{{ article.headline }}</em>
{% endfor %}
<a href="{{ site.url }}{{ site.baseurl }}/allnews.html">see all news</a>

</div>

<div class="col-sm-4" style="display:table-cell; vertical-align:middle; text-align:left">

  <ul style="overflow: hidden">
  <img src="{{ site.url }}{{ site.baseurl }}/images/profile_pic.jpeg" class="img-responsive" width="100%" />
  </ul>

  <!-- <br clear="all" /> -->

  <!-- <A HREF="mailto:tejank10@gmail.com">Email</A> <br>-->
  <!-- Google Research India<br> -->
  <!-- Bengaluru, KA<br> -->


</div>

</div>
</div>
