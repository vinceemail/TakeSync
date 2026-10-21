"""Optional command-line entry point for repeatable testing and batch use."""
from pathlib import Path
import argparse


def main():
    parser = argparse.ArgumentParser(description='TakeSync local alignment engine')
    parser.add_argument('camera_a'); parser.add_argument('camera_b'); parser.add_argument('master')
    parser.add_argument('--output', required=True, help='Output .takesync project')
    parser.add_argument('--xml', help='Also export an FCPXML timeline')
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--tolerance', type=int, default=2)
    parser.add_argument('--fps', default=None)
    parser.add_argument('--in', dest='start', type=float, default=0)
    parser.add_argument('--out', dest='end', type=float, default=0)
    parser.add_argument('--cache', default=None)
    args = parser.parse_args()
    from .engine import align
    from .media import probe
    cache = Path(args.cache) if args.cache else Path(args.output).resolve().parent/'.takesync-cache'
    search = None
    if args.start or args.end:
        search = (args.start, args.end or probe(args.camera_a, True).duration)
    def report(value, text):
        print(f'{value:6.1%} {text}', flush=True)
    project = align(args.camera_a, args.camera_b, args.master, cache,
                    args.tolerance, args.fps, search, report)
    project.save(args.output)
    if args.xml:
        from .fcpxml import export
        export(project, args.xml)
    if args.preview:
        from .preview import render
        print(render(project, cache, progress=report))
    print(f'{len(project.sections)} sections, {len(project.anchors)} anchors; '
          f'camera B delta {project.camera_delta:.4f}s; {sum(a.review for a in project.anchors)} review points')


if __name__ == '__main__':
    main()
