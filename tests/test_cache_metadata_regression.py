import os


def test_metadata_only_budget_is_best_effort(tmp_path):
    from services import longform_render as lr
    metadata = tmp_path / "voices_roots.json"
    metadata.write_text('["/old/voices"]')
    size = metadata.stat().st_size
    assert lr.prune_cache_dir(str(tmp_path), max_bytes=0) == (size, 0)
    assert metadata.exists()


def test_interrupted_audio_files_still_share_the_budget(tmp_path):
    from services import longform_render as lr
    index = tmp_path / lr.VOICES_ROOTS_FILE
    index.write_text('["/old/voices"]')
    inputs = tmp_path / lr.CHAPTER_INPUTS_SUBDIR
    inputs.mkdir()
    (inputs / "chapter.json").write_text('{"inputs": []}')
    partial = tmp_path / "chapter.wav.part"
    partial.write_bytes(b"partial" * 100)
    os.utime(index, (1, 1))
    os.utime(partial, (2, 2))
    metadata_size = index.stat().st_size + (inputs / "chapter.json").stat().st_size
    assert lr.prune_cache_dir(str(tmp_path), max_bytes=metadata_size) == (metadata_size, 1)
    assert not partial.exists() and index.exists() and (inputs / "chapter.json").exists()
