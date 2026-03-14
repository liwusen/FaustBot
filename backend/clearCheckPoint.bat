@echo off
cd %~dp0
del agents/faust/faust_checkpoint.db
if exist faust_checkpoint.db-shm del agents/faust/faust_checkpoint.db-shm
if exist faust_checkpoint.db-wal del agents/faust/faust_checkpoint.db-wal
echo Checkpoint database 'faust_checkpoint.db' has been cleared.
pause