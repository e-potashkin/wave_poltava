.PHONY: test clean

test:
	python3 tests/test_feed.py
	python3 tests/test_coordinator.py
	python3 tests/test_markers.py
	python3 tests/test_districts.py
	python3 tests/test_markers_flow.py
	python3 tests/test_tracker.py

clean:
	rm -rf custom_components/wave_poltava/__pycache__ tests/__pycache__
