# R1-A1 Acceptance Prompts — 42 Testable Behaviors

Each prompt is a user-facing instruction that must produce a verifiable
behavior in the system. Tests in `tests/` assert the module-level
behavior each prompt exercises. Format: prompt → expected module path.

## Voice & Brain
1. "R1, say hello." → `brain.agent` responds via `audio.speaker`
2. "What model are you running right now?" → `brain.llm_client` reports active model tag
3. "Switch to your small model." → `brain.llm_client` loads fallback model
4. "Remember that my name is Walker." → `brain.memory` stores the fact
5. "What's my name?" → recall from `brain.memory`
6. "Summarize the last thing I asked you." → conversation buffer recall
7. "Speak in a happy tone." → `audio.chirp` selects happy phrase set
8. "Be quiet for the next five minutes." → `audio.mute_until` timer set

## Motion & Navigation
9. "Drive forward one meter." → `motion.drive` odometry closed loop
10. "Turn around." → `motion.rotate(180)` within ±3°
11. "Follow me slowly." → `motion.follow` engages camera-tracked target
12. "Stop right now." → `motion.estop_soft` halts within 100 ms
13. "Are your wheels blocked?" → bump-switch + current-sense report
14. "Go into three-leg mode." → `motion.center_leg.deploy()` + posture shift
15. "Go back to two-leg mode." → retract + tilt lock
16. "Wiggle excitedly." → `motion.express("wiggle")` canned gait
17. "What's your battery range estimate?" → `power.estimate_range_m()`

## Dome & Eye
18. "Look at me." → `eye.track_face()` + dome servo centering
19. "Rotate your dome 90 degrees to the left." → `dome.rotate_deg(-90)` ±2°
20. "Spin your dome like you're confused." → `dome.express("confused")`
21. "What do you see right now?" → `eye.snapshot()` + vision-LLM caption
22. "Wink at me twice." → `eye.wink(count=2)` LED + shutter servo
23. "Is anyone in front of you?" → face detection boolean
24. "Read the text on that sign." → OCR path on `eye.snapshot()`
25. "How bright is it in here?" → camera exposure telemetry report

## Display & Projector
26. "Show a smile on your screen." → `display.show("smile")`
27. "Show your battery level on your chest screen." → `display.gauge(power.soc())`
28. "Display a scrolling message that says HELLO." → `display.scroll_text()`
29. "Turn your screen off." → `display.sleep()`
30. "Project a map of this room." → `projector.show(frame="map")`
31. "Project what your eye sees." → projector mirrors camera feed
32. "Stop projecting." → `projector.off()` lamp kill + fan cooldown
33. "Dim the projector to half brightness." → `projector.set_brightness(0.5)`

## Thermal & Power
34. "How hot is your brain?" → `thermal.report()` host + probe temps
35. "Are any of your fans failing?" → tach check on all 5 fans
36. "Pretend you're overheating." → `thermal.simulate(90)` triggers throttle path
37. "How much charge do you have left?" → `power.soc()` percentage
38. "Should you go charge now?" → `power.should_seek_charger()` policy
39. "Shut your brain down but keep your wheels alive." → host soft-off via MCU relay

## Spatial Awareness (the 8 upgrades)
43. "Is a person nearby?" → `awareness.mmwave.human_present()` (LD2450 radar, works in the dark)
44. "How close is the nearest obstacle?" → `awareness.fusion` nearest across mmWave + ultrasonic
45. "Watch out, there's a step." → `awareness.cliff.is_cliff()` + forced stop
46. "Which way is safest to turn?" → `awareness.cliff.safest_turn()`
47. "Hold this heading straight." → `awareness.pose` IMU/odometry complementary filter
48. "Slow down near the furniture." → `awareness.proximity` zone policy scales drive speed
49. "Remember this room's layout." → `awareness.occupancy` grid with confidence decay
50. "Follow that person at one meter." → `motion.refine.follow_target()` mmWave-tracked pursuit

## System & Meta
51. "Run a full self-check." → `interconnect.selftest` all links green
52. "Which of your sensors is not responding?" → health matrix diff
53. "Reboot your brain and come back online cleanly." → service restart + re-handshake within 30 s
