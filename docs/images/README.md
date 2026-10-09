# How banner.jpg was made

ComfyUI 0.38.2 with Z-Image Turbo (z_image_turbo_bf16), 1536x512, seed 33, the workflow in banner-workflow.api.json (node 4's {SUBJECT} replaced by the prompt below), picked from seeds 11, 22, 33 and 44, saved as JPEG quality 84. No text or marks in the corners.

Prompt: flat vector illustration, wide web banner, deep navy blue background with subtle grid, soft glowing teal line chart and small rising bar charts flowing from left to right into an open archive box on the right that catches the data points, calm, minimal, clean geometric shapes, gentle gradients, plenty of empty space, no text, no letters, no numbers, no logos

The chart daily-views.png is drawn by chartwright from daily-views.vl.json and sample-daily.csv, which make_sample_data.py builds by running repo-traffic through the golden harness on invented traffic for invented repos (no network). PNG quantized to 48 colours.
